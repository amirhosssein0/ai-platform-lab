from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from app.metrics import record_pii_detection

MAX_MESSAGE_LENGTH = 4000

_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()


class InputValidationError(Exception):
    pass


def validate_input(message: str) -> None:
    if not message or not message.strip():
        raise InputValidationError("Message cannot be empty")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise InputValidationError(f"Message exceeds {MAX_MESSAGE_LENGTH} character limit")


def redact_pii(text: str) -> str:
    if not text or not text.strip():
        return text
    results = _analyzer.analyze(text=text, language="en")
    if not results:
        return text
    for result in results:
        record_pii_detection(entity_type=result.entity_type)
    anonymized = _anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text