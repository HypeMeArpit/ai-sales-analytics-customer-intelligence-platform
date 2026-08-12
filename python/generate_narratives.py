"""
Generates plain-English narrative summaries from the ML outputs
(customer_segments, transaction_anomalies) using a local Ollama model,
and stores them in the `narratives` table.

Lives in: python/generate_narratives.py
Run from the python/ folder with: python generate_narratives.py

Requires Ollama running locally with the model pulled:
  ollama list                 # check what's installed
  ollama pull llama3.2:3b     # if it's missing
"""

import json
from typing import Optional

import ollama
import pandas as pd
from sqlalchemy import text

from connection import get_connection, get_engine

MODEL = "llama3.2:3b"

SYSTEM_PROMPT = (
    "You are a data analyst writing a short, plain-English summary for a "
    "business audience. Use ONLY the numbers and facts given to you below - "
    "do not invent, estimate, or infer any figures, names, countries, or "
    "other specifics that are not explicitly provided. If you mention a "
    "specific fact (a country, a number, a name), it must appear verbatim "
    "in the input below - never substitute a similar-sounding fact (e.g. "
    "do not swap one country for a neighboring one). Do not restate every "
    "number; pick the ones that matter and explain what they mean for the "
    "business. End with one concrete, specific action - not generic "
    "language like 'personalized offers' or 'maximize growth'. Keep it to "
    "3-4 sentences, no bullet points, no headers, no markdown."
)

# Common sentence-starting words that would otherwise trigger false positives
# in the fact-verification check below (capitalized only by position, not
# because they're a proper noun).
_COMMON_SENTENCE_STARTERS = {
    "our", "this", "these", "those", "given", "by", "we", "it", "the",
    "a", "an", "these", "that", "with", "as", "since", "while", "in",
    "for", "to", "and", "but", "so", "average", "customers", "segment",
}


def check_ollama_ready() -> None:
    """Fail fast with a clear message if Ollama or the model isn't available."""
    try:
        models = ollama.list()
    except Exception as e:
        raise RuntimeError(
            "Couldn't reach Ollama. Is it running? It usually runs as a "
            "background service after install — if not, run `ollama serve` "
            "in a separate terminal and try again."
        ) from e

    names = [m.get("model", m.get("name", "")) for m in models.get("models", [])]
    if not any(MODEL in n for n in names):
        raise RuntimeError(
            f"Model '{MODEL}' isn't pulled locally yet. Run: ollama pull {MODEL}"
        )
    print(f"✅ Ollama is running and '{MODEL}' is available.")


# ---------------------------------------------------------------------------
# Data fetching — all aggregated, none of this touches raw transaction rows
# ---------------------------------------------------------------------------

def fetch_segment_stats() -> pd.DataFrame:
    query = """
        SELECT
            segment_name,
            COUNT(*)                     AS customer_count,
            ROUND(AVG(recency_days), 1)  AS avg_recency_days,
            ROUND(AVG(frequency), 1)     AS avg_frequency,
            ROUND(AVG(monetary), 2)      AS avg_monetary
        FROM customer_segments
        GROUP BY segment_name
        ORDER BY avg_monetary DESC
    """
    return pd.read_sql(query, con=get_engine())


def fetch_anomaly_overview() -> dict:
    query = """
        SELECT
            SUM(is_anomaly)                                AS total_anomalies,
            COUNT(*)                                        AS total_scored,
            ROUND(100.0 * SUM(is_anomaly) / COUNT(*), 2)     AS pct_anomalous
        FROM transaction_anomalies
    """
    row = pd.read_sql(query, con=get_engine()).iloc[0]
    return row.to_dict()


def fetch_top_flagged_customers(limit: int = 3) -> pd.DataFrame:
    query = f"""
        SELECT
            t.customer_id,
            COUNT(*)                                      AS anomaly_count,
            ROUND(AVG(t.quantity), 1)                     AS avg_quantity,
            ROUND(AVG(t.quantity * t.unit_price), 2)      AS avg_order_value,
            MAX(t.country)                                AS country
        FROM transaction_anomalies ta
        JOIN transactions t ON t.id = ta.transaction_id
        WHERE ta.is_anomaly = 1 AND t.customer_id IS NOT NULL
        GROUP BY t.customer_id
        ORDER BY anomaly_count DESC
        LIMIT {limit}
    """
    return pd.read_sql(query, con=get_engine())


# ---------------------------------------------------------------------------
# Ollama call + persistence
# ---------------------------------------------------------------------------

def call_ollama(user_prompt: str) -> str:
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response["message"]["content"].strip()


def verify_narrative_facts(narrative_text: str, input_stats: dict) -> list:
    """
    Lightweight guard against the exact failure mode we found (the model
    substituting 'Netherlands' for 'Ireland'): pull out capitalized words
    from the narrative that look like proper nouns, and flag any that don't
    appear anywhere in the input_stats fed to the model.

    Not bulletproof — misses lowercase hallucinations and can flag
    legitimate words that happen to be capitalized — but it catches this
    specific class of error automatically instead of relying on a human to
    notice it.
    """
    import re

    source_text = json.dumps(input_stats, default=str).lower()

    candidates = re.findall(r"\b[A-Z][a-zA-Z]+\b", narrative_text)
    flagged = []
    for word in candidates:
        if word.lower() in _COMMON_SENTENCE_STARTERS:
            continue
        if word.lower() not in source_text:
            flagged.append(word)

    if flagged:
        print(f"⚠️  Possible unverified fact(s) in narrative: {sorted(set(flagged))}")
    return flagged


def save_narrative(
    narrative_type: str,
    reference_key: Optional[str],
    input_stats: dict,
    narrative_text: str,
) -> None:
    """
    Upsert on (narrative_type, reference_key) instead of a plain INSERT.
    Requires sql/migrations/006_add_narratives_unique_key.sql to have been
    applied — that migration adds the unique key this relies on (it also
    handles reference_key being NULL for the 'executive' narrative, which a
    plain UNIQUE index on a nullable column wouldn't enforce correctly, since
    MySQL treats multiple NULLs as distinct under a normal unique index).

    A rerun therefore updates the existing row in place (refreshing
    input_stats, narrative_text, and generated_at) rather than appending a
    new one — narratives now behaves the same way customer_segments and
    transaction_anomalies already do on rerun, just via upsert instead of
    truncate, since a narrative is "current state for this type/key" rather
    than a full-table rebuild each run.
    """
    with get_connection() as conn:
        conn.execute(
            text(
                """
                INSERT INTO narratives (narrative_type, reference_key, input_stats, narrative_text)
                VALUES (:t, :k, :s, :n)
                ON DUPLICATE KEY UPDATE
                    input_stats    = VALUES(input_stats),
                    narrative_text = VALUES(narrative_text),
                    generated_at   = CURRENT_TIMESTAMP
                """
            ),
            {
                "t": narrative_type,
                "k": reference_key,
                "s": json.dumps(input_stats, default=str),
                "n": narrative_text,
            },
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Narrative builders
# ---------------------------------------------------------------------------

def generate_segment_narratives(segment_df: pd.DataFrame) -> dict:
    narratives = {}
    for _, row in segment_df.iterrows():
        stats = row.to_dict()
        prompt = (
            f"Segment: {stats['segment_name']}\n"
            f"Number of customers: {stats['customer_count']}\n"
            f"Average days since last purchase: {stats['avg_recency_days']}\n"
            f"Average number of orders: {stats['avg_frequency']}\n"
            f"Average total spend: ${stats['avg_monetary']}\n\n"
            "Write a short summary of this customer segment for a business "
            "stakeholder, including one suggested action for this group."
        )
        narrative = call_ollama(prompt)
        flagged = verify_narrative_facts(narrative, stats)
        stats["_flagged_terms"] = flagged
        save_narrative("segment", stats["segment_name"], stats, narrative)
        narratives[stats["segment_name"]] = narrative
        print(f"✅ Segment narrative generated: {stats['segment_name']}")
    return narratives


def generate_anomaly_narrative(overview: dict, top_customers: pd.DataFrame) -> str:
    top_lines = "\n".join(
        f"- Customer {r.customer_id}: {r.anomaly_count} flagged transactions, "
        f"avg {r.avg_quantity} units/order, avg order value ${r.avg_order_value}, "
        f"country: {r.country}"
        for r in top_customers.itertuples()
    )
    prompt = (
        f"Total transactions scored: {overview['total_scored']}\n"
        f"Flagged as anomalous: {overview['total_anomalies']} "
        f"({overview['pct_anomalous']}%)\n\n"
        f"Top flagged accounts:\n{top_lines}\n\n"
        "Write a short summary explaining what this anomaly detection found, "
        "for a non-technical business stakeholder. A statistical anomaly is "
        "NOT automatically fraud - it means 'unusual compared to typical "
        "behavior'. The pattern here appears to be large bulk orders from a "
        "few repeat accounts, not data errors or fraud - make sure the "
        "summary doesn't wrongly imply fraud."
    )
    stats_for_storage = {
        "overview": overview,
        "top_customers": top_customers.to_dict(orient="records"),
    }
    narrative = call_ollama(prompt)
    flagged = verify_narrative_facts(narrative, stats_for_storage)
    stats_for_storage["_flagged_terms"] = flagged
    save_narrative("anomaly", "anomaly_overview", stats_for_storage, narrative)
    print("✅ Anomaly narrative generated")
    return narrative


def generate_executive_narrative(segment_narratives: dict, anomaly_narrative: str) -> str:
    segments_block = "\n\n".join(
        f"Segment - {name}: {narrative}" for name, narrative in segment_narratives.items()
    )
    prompt = (
        "Below are summaries already written about customer segments and "
        "transaction anomalies. Combine them into a single short executive "
        "summary (3-4 sentences) a business owner could read in under 30 "
        "seconds. Do not introduce any new numbers - only synthesize what is "
        "stated below.\n\n"
        f"{segments_block}\n\nAnomalies: {anomaly_narrative}"
    )
    stats_for_storage = {
        "segment_narratives": segment_narratives,
        "anomaly_narrative": anomaly_narrative,
    }
    narrative = call_ollama(prompt)
    flagged = verify_narrative_facts(narrative, stats_for_storage)
    stats_for_storage["_flagged_terms"] = flagged
    save_narrative("executive", None, stats_for_storage, narrative)
    print("✅ Executive narrative generated")
    return narrative


if __name__ == "__main__":
    import sys

    # Optional: `python generate_narratives.py anomaly` regenerates just the
    # anomaly narrative — handy for testing a prompt fix without rerunning
    # everything (and appending duplicate segment/executive rows).
    only = sys.argv[1] if len(sys.argv) > 1 else None

    check_ollama_ready()

    if only in (None, "segment"):
        segment_df = fetch_segment_stats()
        segment_narratives = generate_segment_narratives(segment_df)

    if only in (None, "anomaly"):
        overview = fetch_anomaly_overview()
        top_customers = fetch_top_flagged_customers()
        anomaly_narrative = generate_anomaly_narrative(overview, top_customers)

    if only is None:
        generate_executive_narrative(segment_narratives, anomaly_narrative)

    print("\n✅ Done — narrative(s) saved to the `narratives` table.")