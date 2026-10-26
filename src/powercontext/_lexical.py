# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Small, deterministic lexical features for offline evidence ranking."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

_STOP_WORDS = frozenset([
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "more",
    "most",
    "not",
    "of",
    "on",
    "or",
    "our",
    "should",
    "than",
    "that",
    "the",
    "their",
    "these",
    "they",
    "this",
    "those",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "using",
    "use",
    "based",
    "given",
    "please",
    "provide",
    "answer",
    "question",
    "state",
    "report",
    "reported",
    "according",
    "respectively",
    "following",
    "shown",
    "details",
    "fiscal",
    "fy",
    "year",
    "years",
])


def terms(text: str) -> tuple[str, ...]:
    """Normalize inflections while retaining numbers and non-Latin words."""

    result = []
    for word in re.findall(r"[^\W_]+", text.casefold()):
        if word in _STOP_WORDS:
            continue
        if word.isascii() and word.isalpha():
            if len(word) > 5 and word.endswith("ies"):
                word = word[:-3] + "y"
            elif len(word) > 5 and word.endswith("ing"):
                word = word[:-3]
                if len(word) > 2 and word[-1] == word[-2]:
                    word = word[:-1]
            elif len(word) > 4 and word.endswith("ed"):
                word = word[:-2]
            elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
                word = word[:-1]
            # Match e.g. calibrate/calibrated, activate/activated after stripping -ed.
            if len(word) > 4 and word.endswith("e"):
                word = word[:-1]
        result.append(word)
    return tuple(result)


class LexicalRanker:
    """BM25 statistics derived solely from the supplied candidate text."""

    def __init__(self, documents: Sequence[str]) -> None:
        self.counts = tuple(Counter(terms(document)) for document in documents)
        self.lengths = tuple(sum(count.values()) for count in self.counts)
        self.average_length = sum(self.lengths) / max(1, len(self.lengths)) or 1
        frequencies = Counter(term for count in self.counts for term in count)
        self.idf = {
            term: math.log(1 + (len(documents) - count + 0.5) / (count + 0.5)) for term, count in frequencies.items()
        }

    def score(self, index: int, query: dict[str, float], *, length_weight: float = 0.6) -> float:
        count = self.counts[index]
        normalization = 1.2 * (1 - length_weight + length_weight * self.lengths[index] / self.average_length)
        return sum(
            weight * self.idf.get(term, 0) * count[term] * 2.2 / (count[term] + normalization)
            for term, weight in query.items()
            if count[term]
        )
