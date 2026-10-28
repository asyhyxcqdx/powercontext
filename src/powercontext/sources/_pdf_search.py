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

"""Offline query planning and complementary financial-statement page ranking."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from powercontext._lexical import LexicalRanker, terms

if TYPE_CHECKING:
    from powercontext.builtin.artifacts.memory import MemoryHit


@dataclass(frozen=True)
class _Section:
    trigger: str
    heading: str
    probes: tuple[str, ...]
    tabular: bool = True


_SECTIONS = (
    _Section(
        r"income statement|statements? of (?:income|operations|earnings)|p\s*&\s*l|earnings|"
        r"(?:net|operating) (?:income|profit)|gross (?:profit|margin)|ebit(?:da)?|profit margin|cost of (?:sales|goods)|"
        r"operating[-\s]+margin|capital[-\s]+intensiv|cash flow conversion|tax rate",
        r"\b(?:statements? of (?:income|operations|earnings)|income statements?|profit and loss)\b",
        ("statement income", "statement operations", "net revenue operating profit"),
    ),
    _Section(
        r"tax rate|financial performance",
        r"\b(?:summary of financial (?:performance|results)|selected financial data|income taxes)\b",
        ("summary financial performance", "effective tax rate", "income taxes"),
        tabular=False,
    ),
    _Section(
        r"(?:product|service) categor|segment.*(?:sales|revenue)|(?:sales|revenue).*segment",
        r"\b(?:summary of )?(?:business )?segment (?:data|information|results)\b",
        ("business segment data", "segment revenue", "segment sales"),
        tabular=False,
    ),
    _Section(
        r"cash flow|ebitda|capex|depreciation|capital (?:expenditure|spending)|cash (?:provided|generated|used)|"
        r"capital[-\s]+intensiv",
        r"\b(?:statements? of cash flows?|cash flows? statements?)\b",
        ("statement cash flows", "depreciation amortization", "capital expenditures"),
    ),
    _Section(
        r"balance sheet|assets?|liabilit|working capital|current ratio|quick ratio|debt|receivables?|inventor|"
        r"capital[-\s]+intensiv",
        r"\b(?:balance sheets?|statements? of financial (?:position|condition))\b",
        ("balance sheet", "financial position", "current assets liabilities"),
    ),
    _Section(
        r"shareholders? equity|stockholders? equity|dividend|share repurchase|buyback",
        r"\bstatements? of (?:changes in )?(?:(?:stock|share)holders.? )?equity\b",
        ("statement equity", "dividends repurchases"),
    ),
    _Section(
        r"geograph|countr|territor|operates|regions?|segments?|(?:useful|relevant) metric",
        r"\b(?:geograph\w*|our divisions|our business|business overview|operating segments?|"
        r"reportable segments?|business segments?|description of (?:the )?business|item\s*1[.:]?\s*business)\b",
        ("geographic countries", "segments divisions", "countries territories", "business overview"),
        tabular=False,
    ),
    _Section(
        r"legal|litigation|lawsuit|battles|proceedings",
        r"\b(?:legal proceedings|litigation|legal contingencies|commitments and contingencies)\b",
        ("legal proceedings", "litigation contingencies", "material legal"),
        tabular=False,
    ),
)

_SYNONYMS = (
    (r"restructur", "restructuring impairment charges costs expenses"),
    (r"revenues?|sales", "revenue revenues net sales"),
    (r"capex|capital expenditure", "capital spending expenditures property plant equipment purchases additions"),
    (r"operating income", "operating profit"),
    (r"net profit", "net income earnings"),
    (r"cogs|cost of goods", "cost goods sales revenues"),
    (r"\bm\s*&\s*a\b|mergers? and acquisitions?", "acquisitions divestitures organic growth"),
    (r"capital[-\s]+intensiv", "property plant equipment capital expenditures assets revenue"),
    (r"operating[-\s]+margin", "operating income revenue sales"),
    (r"cash flow conversion", "operating cash flow net income capital expenditures"),
    (r"customers?|clients?", "customers clients purchasers buyers sales"),
    (r"concentration", "concentration significant largest major percent revenues"),
    (r"retain|retention", "retention retain attrition loyalty existing members"),
    (r"cyclical|cyclicality", "cyclical cycles economic downturn demand"),
    (r"tax rate", "effective income tax expense benefit provision rate"),
    (r"legal|litigation|lawsuit|battles", "litigation lawsuit proceedings claims contingencies settlement"),
)
_INSTRUCTIONS = frozenset(
    terms(
        "give response respond calculate define assume assuming perspective analyst rely relying "
        "only directly explicitly outlined primarily important quantity unadjusted millions USD "
        "materially ongoing financial information company amount many much total per any"
    )
)


@dataclass(frozen=True)
class PDFSearchQuery:
    question: str
    sections: tuple[_Section, ...]
    probes: tuple[str, ...]
    weights: dict[str, float]


def plan_pdf_query(question: str) -> PDFSearchQuery:
    """Split a multi-statement question into bounded independent recall probes."""

    normalized = re.sub(r"\bfy\s*(?=\d{4}\b)", "", question.casefold())
    normalized = re.sub(r"\bcash[-\s]*flows?\b", "cash flow", normalized)
    sections = tuple(section for section in _SECTIONS if re.search(section.trigger, normalized))
    weights = {word: 1.0 for word in terms(normalized) if word not in _INSTRUCTIONS and not word.isdecimal()}
    probes = [question]
    for section in sections:
        probes.extend(section.probes)
    for trigger, expansion in _SYNONYMS:
        if re.search(trigger, normalized):
            probes.append(expansion)
            # FTS backends may interpret multiword probes conjunctively.
            # Separate alternatives retrieve pages using only one synonym.
            probes.extend(expansion.split())
            for word in terms(expansion):
                weights.setdefault(word, 0.5)
    for section in sections:
        for word in terms(" ".join(section.probes)):
            weights.setdefault(word, 0.35)
    probes.extend(word for word in re.findall(r"[^\W_]+", question) if set(terms(word)) & weights.keys())
    return PDFSearchQuery(question, sections, tuple(dict.fromkeys(probes)), weights)


def _document_priors(hits: list[MemoryHit], question: str) -> list[float]:
    # Preserve digits: short company identifiers such as R7 must remain distinct
    # from unrelated documents. Spaces and punctuation do not affect a name match.
    query_tokens = re.findall(r"[a-z0-9]+", question.casefold())
    query_names = {
        "".join(query_tokens[start:end])
        for start in range(len(query_tokens))
        for end in range(start + 1, min(start + 6, len(query_tokens)) + 1)
    }
    documents = [hit.text.partition("\n")[0] for hit in hits]
    named = set()
    aliases_by_document = {}
    for document in set(documents):
        prefix = re.split(r"(?:19|20)\d{2}", document, maxsplit=1)[0]
        words = re.findall(r"[a-z0-9]+", prefix.casefold())
        aliases = {"".join(words)}
        # Legal suffixes are commonly present in document identifiers but
        # omitted in questions. Keep digits and substantive name words intact.
        while len(words) > 1 and words[-1] in {
            "inc",
            "incorporated",
            "corp",
            "corporation",
            "ltd",
            "limited",
            "plc",
            "llc",
            "co",
            "company",
        }:
            words.pop()
            aliases.add("".join(words))
        aliases_by_document[document] = aliases
        if any(len(company) >= 2 and company in query_names for company in aliases):
            named.add(document)
    # Infer exchange symbols from the retrieved text, not a company/ticker
    # dictionary. Require the document's own name immediately before the
    # exchange annotation so a counterparty ticker alone is not an identity.
    for hit, document in zip(hits, documents, strict=True):
        body = hit.text.partition("\n")[2]
        for match in re.finditer(r"\b(?:NYSE|NASDAQ|AMEX|LSE|TSX|ASX|HKEX)\s*:\s*([A-Z][A-Z0-9.-]{0,9})\b", body):
            symbol = re.sub(r"[^a-z0-9]", "", match[1].casefold())
            if symbol not in query_names:
                continue
            context = re.sub(r"[^a-z0-9]", "", body[max(0, match.start() - 200) : match.start()].casefold())
            if any(len(alias) >= 2 and alias in context for alias in aliases_by_document[document]):
                named.add(document)
    years = set(re.findall(r"(?:19|20)\d{2}", question))
    return [
        (0.02 if named and document not in named else 1.0)
        * (1.15 if years & set(re.findall(r"(?:19|20)\d{2}", document)) else 1.0)
        for document in documents
    ]


def _heading_lines(body: str) -> Iterator[tuple[int, str]]:
    lines = [" ".join(line.split()) for line in body.splitlines()]
    for position in range(len(lines)):
        combined = ""
        for line in lines[position : position + 3]:
            if not line:
                break
            combined = f"{combined} {line}".strip()
            if len(combined) > 160:
                break
            yield position, combined


def _heading_score(body: str, section: _Section) -> float:
    matches = []
    for position, line in _heading_lines(body):
        match = re.search(section.heading, line, re.I)
        if len(line) > 160 or match is None:
            continue
        # A reference in prose or the table of contents is not the statement itself.
        if re.search(r"\b(?:see|refer|notes to|discussed|included in|index to)\b|\.{2,}|\s\d{1,4}$", line, re.I):
            continue
        prefix, suffix = line[: match.start()].strip(), line[match.end() :].strip()
        if not _heading_affixes(prefix, suffix, tabular=section.tabular):
            continue
        confidence = 2.0 if re.search(r"\b(?:consolidated|condensed|combined)\b", prefix, re.I) else 1.0
        matches.append(confidence * (1.5 if position < 12 else 1.0))
    if not matches:
        return 0.0
    if not section.tabular:
        return max(matches)
    numeric_values = len(re.findall(r"\b\d[\d,.]*\b", body))
    return max(matches) * (1 + min(2.0, numeric_values / 25))


def _heading_affixes(prefix: str, suffix: str, *, tabular: bool) -> bool:
    if tabular:
        # Line wrapping can make a prose reference short. Require the words
        # preceding the statement name to actually be heading qualifiers.
        return bool(
            re.fullmatch(
                r"(?:(?:consolidated|condensed|combined|audited|unaudited|annual|financial)\s*)*", prefix, re.I
            )
            and re.fullmatch(
                r"(?:\s|[()./:\u2014\u2013-]|continued|unaudited|and|comprehensive|income|loss|losses)*", suffix, re.I
            )
        )
    return bool(
        re.fullmatch(r"(?:(?:item|note|table)\s*\d+[a-z]?\s*[.:\u2014\u2013-]?\s*)?", prefix, re.I)
        and not re.search(r"\b(?:is|are|was|were|has|have|which|that|could|may|include)\b", suffix, re.I)
    )


def _lexical_scores(bodies: list[str], weights: dict[str, float], question: str = "") -> list[float]:
    ranker = LexicalRanker(bodies)
    passages: list[str] = []
    owners: list[int] = []
    for index, body in enumerate(bodies):
        words = body.split()
        for start in range(0, len(words), 80):
            passages.append(" ".join(words[start : start + 160]))
            owners.append(index)
    passage_ranker = LexicalRanker(passages)
    passage_scores = [0.0] * len(bodies)
    for index, owner in enumerate(owners):
        passage_scores[owner] = max(passage_scores[owner], passage_ranker.score(index, weights))
    # Preserve local phrases: repeated isolated words in a long report should
    # not outweigh a short passage discussing the actual requested concept.
    query_terms = [word for word in terms(question) if word in weights and weights[word] >= 1]
    pairs = set(pairwise(query_terms))
    phrase_scores = []
    for body in bodies:
        tokens = terms(body)
        adjacent = set(pairwise(tokens))
        phrase_scores.append(
            sum(min(ranker.idf.get(left, 0), ranker.idf.get(right, 0)) for left, right in pairs & adjacent)
        )
    return [
        ranker.score(index, weights) + 0.35 * passage_scores[index] + 2 * phrase_scores[index]
        for index in range(len(bodies))
    ]


def rank_pdf_candidates(hits: list[MemoryHit], query: PDFSearchQuery, limit: int) -> list[int]:
    """Keep complementary statement pages alongside the general lexical ranking."""

    bodies = [hit.text.partition("\n")[2] for hit in hits]
    priors = _document_priors(hits, query.question)
    # A company name selects the document; its repetition in headers, stock
    # plans and boilerplate is not evidence relevance within that document.
    identity_terms = set()
    for hit in hits:
        prefix = re.split(r"(?:19|20)\d{2}", hit.text.partition("\n")[0], maxsplit=1)[0]
        identity_terms.update(terms(prefix.replace("_", " ")))
    weights = {word: weight for word, weight in query.weights.items() if word not in identity_terms}
    lexical = _lexical_scores(bodies, weights or query.weights, query.question)
    maximum = max(lexical, default=0) or 1
    scores = [score / maximum * prior for score, prior in zip(lexical, priors, strict=True)]
    rankings = []
    for section in query.sections:
        headings = [_heading_score(body, section) * prior for body, prior in zip(bodies, priors, strict=True)]
        ranking = sorted(
            (index for index, score in enumerate(headings) if score > 0 and priors[index] >= 1),
            key=lambda index: (-headings[index], -scores[index], hits[index].entry_id),
        )
        rankings.append(ranking)
        for rank, index in enumerate(ranking):
            scores[index] += 1 / (1 + rank)
    selected: list[int] = []
    # Reserve a small portion for each requested statement. A verbose management
    # discussion cannot displace every page of a less wordy numeric statement.
    quota = min(3, max(1, limit // max(1, len(rankings))))
    for depth in range(quota):
        for ranking in rankings:
            if depth < len(ranking) and ranking[depth] not in selected:
                selected.append(ranking[depth])
    ordered = sorted(range(len(hits)), key=lambda index: (-scores[index], hits[index].entry_id))
    selected.extend(index for index in ordered if index not in selected)
    return selected
