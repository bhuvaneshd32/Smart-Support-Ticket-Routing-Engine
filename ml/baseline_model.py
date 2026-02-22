# ml/baseline_model.py

import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from data.training_samples import TRAINING_DATA

# Prepare data
texts = [item[0] for item in TRAINING_DATA]
labels = [item[1] for item in TRAINING_DATA]

_vectorizer = TfidfVectorizer(stop_words="english")
_X = _vectorizer.fit_transform(texts)

_classifier = LogisticRegression(max_iter=500)
_classifier.fit(_X, labels)

_URGENCY_KEYWORDS = [
    r"\burgent\b",
    r"\basap\b",
    r"\bimmediately\b",
    r"\bcritical\b",
    r"\bbroken\b",
    r"\bnot working\b",
    r"\boutage\b",
    r"\bdown\b",
]


def baseline_classify(text: str) -> str:
    if not text.strip():
        return "Technical"

    X = _vectorizer.transform([text])
    prediction = _classifier.predict(X)[0]
    return prediction


def baseline_urgency_score(text: str) -> float:
    if not text.strip():
        return 0.0

    text_lower = text.lower()
    matches = sum(1 for pattern in _URGENCY_KEYWORDS if re.search(pattern, text_lower))

    score = min(matches / 5, 1.0)
    return float(score)
