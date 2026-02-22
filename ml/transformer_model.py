# ml/transformer_model.py

import torch
from transformers import pipeline

_device = 0 if torch.cuda.is_available() else -1

_text_classifier = pipeline(
    "text-classification",
    model="distilbert-base-uncased-finetuned-sst-2-english",
    device=_device,
)

_zero_shot_classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",
    device=_device,
)

CATEGORY_KEYWORDS = {
    "Billing": ["refund", "invoice", "payment", "subscription", "billing"],
    "Technical": ["error", "crash", "server", "bug", "down", "not working"],
    "Legal": ["policy", "gdpr", "contract", "legal", "compliance"],
}


def transformer_classify(text: str) -> str:
    if not text.strip():
        return "Technical"

    text_lower = text.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category

    result = _text_classifier(text)[0]

    if result["label"] == "POSITIVE":
        return "Billing"
    else:
        return "Technical"


def transformer_urgency_score(text: str) -> float:
    if not text.strip():
        return 0.0

    candidate_labels = ["urgent", "not urgent"]

    result = _zero_shot_classifier(text, candidate_labels)
    scores = dict(zip(result["labels"], result["scores"]))

    return float(scores.get("urgent", 0.0))
