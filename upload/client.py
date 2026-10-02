"""Small adapter around the Gemini File Search SDK; never log credentials."""
import time
import logging
import httpx
from google import genai
from google.genai import types, errors

MAX_TOKENS = 512
OVERLAP_TOKENS = 64


class GeminiError(RuntimeError):
    pass


class RetryableGeminiError(GeminiError):
    """Temporary failure; mutations must reconcile before they are retried."""


RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}
LOG = logging.getLogger("upload")


def safe_call(function, *args, _retry_read=False, **kwargs):
    attempts = 3 if _retry_read else 1
    for attempt in range(attempts):
        try:
            return function(*args, **kwargs)
        except errors.APIError as exc:
            error_type = RetryableGeminiError if exc.code in RETRYABLE_CODES else GeminiError
            error = error_type(f"Gemini HTTP {exc.code}: request failed.")
        except httpx.TimeoutException as exc:
            error = RetryableGeminiError(f"Gemini request timed out ({type(exc).__name__}); rerun to reconcile saved progress.")
        except httpx.TransportError as exc:
            error = RetryableGeminiError(f"Gemini transport failed ({type(exc).__name__}).")
        except Exception as exc:
            error = GeminiError(f"Gemini request failed ({type(exc).__name__}).")
        # Only reads are retried here. The pipeline reconciles remote state before
        # retrying an upload, since a lost response can hide a successful write.
        if not isinstance(error, RetryableGeminiError) or attempt == attempts - 1:
            raise error from None
        LOG.warning("Temporary Gemini read failure; retry %s/2: %s", attempt + 1, error)
        time.sleep(2 ** attempt)


def document_info(document):
    metadata = {item.key: item.string_value for item in (document.custom_metadata or [])}
    state = getattr(document.state, "value", document.state)
    return {"name": document.name, "state": state, "metadata": metadata}


class GeminiStore:
    def __init__(self, settings):
        self.timeout = settings.timeout
        self.client = genai.Client(api_key=settings.api_key,
                                   http_options=types.HttpOptions(timeout=60000))

    def close(self):
        self.client.close()

    def ensure_store(self, name, owner):
        if name:
            return safe_call(self.client.file_search_stores.get, name=name, _retry_read=True).name
        # Reuse our unique display name if creation succeeded before a local crash.
        display = f"helpcenter-{owner}"
        stores = safe_call(lambda: list(self.client.file_search_stores.list()), _retry_read=True)
        existing = [store for store in stores if store.display_name == display]
        if len(existing) > 1:
            raise GeminiError("Multiple stores match this upload state; set GEMINI_FILE_SEARCH_STORE explicitly.")
        if existing:
            return existing[0].name
        return safe_call(self.client.file_search_stores.create, config={"display_name": display}).name

    def documents(self, store):
        documents = safe_call(lambda: list(self.client.file_search_stores.documents.list(parent=store)), _retry_read=True)
        return [document_info(item) for item in documents]

    def start(self, store, path, metadata):
        return safe_call(self.client.file_search_stores.upload_to_file_search_store,
            file_search_store_name=store, file=str(path), config={
                "mime_type": "text/markdown", "display_name": path.name,
                "custom_metadata": [{"key": key, "string_value": value} for key, value in metadata.items()],
                "chunking_config": {"white_space_config": {
                    "max_tokens_per_chunk": MAX_TOKENS, "max_overlap_tokens": OVERLAP_TOKENS}},
            })

    def wait(self, operation_name):
        operation = types.UploadToFileSearchStoreOperation(name=operation_name)
        deadline = time.monotonic() + self.timeout
        while True:
            operation = safe_call(self.client.operations.get, operation, _retry_read=True)
            if operation.done:
                if operation.error:
                    raise OperationFailed("Gemini indexing failed; the next run will retry this file.")
                if not operation.response or not operation.response.document_name:
                    raise GeminiError("Gemini completed upload without a document name.")
                return self.wait_document(operation.response.document_name, deadline)
            if time.monotonic() >= deadline:
                raise TimeoutError("Gemini indexing is still pending; rerun to resume the saved operation.")
            time.sleep(2)

    def wait_document(self, name, deadline=None):
        deadline = deadline or time.monotonic() + self.timeout
        while True:
            item = document_info(safe_call(self.client.file_search_stores.documents.get, name=name, _retry_read=True))
            if item["state"] == "STATE_ACTIVE":
                return item
            if item["state"] == "STATE_FAILED":
                raise OperationFailed("Gemini document processing failed; rerun to retry.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Document not active yet; rerun to resume.")
            time.sleep(2)

    def delete(self, name):
        try:
            self.client.file_search_stores.documents.delete(name=name, config={"force": True})
        except errors.APIError as exc:
            if exc.code != 404:
                error_type = RetryableGeminiError if exc.code in RETRYABLE_CODES else GeminiError
                raise error_type(f"Gemini cleanup HTTP {exc.code}; rerun to retry cleanup.") from None
        except httpx.TransportError as exc:
            raise RetryableGeminiError(f"Gemini cleanup failed ({type(exc).__name__}).") from None
        except Exception:
            raise GeminiError("Gemini cleanup failed; rerun to retry cleanup.") from None


class OperationFailed(GeminiError):
    pass
