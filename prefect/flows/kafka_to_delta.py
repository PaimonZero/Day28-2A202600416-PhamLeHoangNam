# prefect/flows/kafka_to_delta.py
from kafka import KafkaConsumer
import json, os
import pandas as pd
from datetime import datetime
from pathlib import Path

try:
    from prefect import flow, task
except ImportError:
    def flow(*_args, **_kwargs):
        def decorator(fn):
            return fn
        return decorator

    def task(fn):
        return fn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DELTA_RAW_PATH = os.getenv("DELTA_RAW_PATH", str(PROJECT_ROOT / "delta-lake" / "raw"))

@task
def consume_and_process():
    """Consume data from Kafka topic"""
    consumer = KafkaConsumer(
        "data.raw",
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id="lab28-prefect",
        consumer_timeout_ms=5000,
        value_deserializer=lambda m: json.loads(m.decode())
    )
    records = []
    for msg in consumer:
        records.append(msg.value)

    print(f"Consumed {len(records)} records from Kafka")
    return records

@task
def save_to_delta(records):
    """Save records to Delta Lake (parquet format)"""
    if not records:
        print("No records to save")
        return
    
    df = pd.DataFrame(records)
    # Giả lập Delta Lake bằng parquet (local volume)
    path = DELTA_RAW_PATH
    os.makedirs(path, exist_ok=True)
    df.to_parquet(f"{path}/batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet")
    print(f"Saved {len(df)} records to Delta Lake")

@flow(name="Kafka to Delta Pipeline", log_prints=True)
def kafka_to_delta_flow():
    """Main flow: consume from Kafka and save to Delta Lake"""
    records = consume_and_process()
    save_to_delta(records)

if __name__ == "__main__":
    kafka_to_delta_flow()
