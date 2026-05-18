# Hướng Dẫn Nộp Bài - Lab #28: Full Platform Integration Sprint

## Yêu Cầu Nộp Bài

**Full AI infrastructure platform demo** - từ data ingestion đến model serving với full observability.

## Các Artifacts Cần Nộp

### 1. Source Code
- Folder `lab28/` hoàn chỉnh với tất cả files
- Tất cả integration scripts hoạt động
- Prefect flows đã deploy và schedule

### 2. Screenshots Demo
Chụp màn hình các bước:
- Prefect UI: http://localhost:4200 (flow đang chạy)
- API Gateway call: `curl http://localhost:8000/health`
- Grafana dashboard: http://localhost:3000

### 3. Kết Quả Smoke Tests
Chạy và chụp màn hình kết quả:
```bash
cd lab28
pytest smoke-tests/ -v
```
Kỳ vọng: 5/5 tests passing

### 4. Production Readiness Score
```bash
python scripts/production_readiness_check.py
```
Kỳ vọng: Score >80%

### 5. Documentation
- `README.md` giải thích cách:
  - Start platform: `docker compose up -d`
  - Deploy Prefect flows
  - Run smoke tests
  - Access dashboards (Grafana:3000, Prometheus:9090, Prefect:4200)

## Định Dạng Nộp Bài

Tạo Repo GitHub chứa:
```
lab28_submission_[student_id]
├── lab28/                    # Source code hoàn chỉnh
│   ├── docker-compose.yml
│   ├── prefect/flows/
│   ├── scripts/
│   ├── api-gateway/
│   └── monitoring/
├── screenshots/              # Screenshots demo
│   ├── prefect_ui.png
│   ├── api_gateway.png
│   └── grafana_dashboard.png
├── smoke_tests_results.png   # Screenshot kết quả pytest
├── production_readiness.png  # Screenshot readiness score
└── README.md                # Hướng dẫn setup
```

## Địa Điểm Nộp
Nộp link repo GitHub qua LMS

## Tiêu Chí Chấm Điểm

| Tiêu Chí | Trọng Số | Mô Tả |
|----------|----------|-------|
| Integration Completeness | 40% | Tất cả 10 integration points hoạt động, data flow end-to-end |
| Observability | 25% | Logs, metrics, traces hiển thị; alerts configured |
| Performance | 20% | Latency trong SLO; load tested; không có memory leaks |
| Architecture Quality | 15% | Clean separation, GitOps config, documented decisions |

## Các Vấn Đề Cần Tránh

- Config drift giữa các environments
- Thiếu error handling tại integration points
- Monitoring coverage không hoàn chỉnh
- Không có rollback strategy
- Demo không test trước khi nộp

## 5 Câu Hỏi Cần Trả Lời Khi Nộp

1. **Phân tích các trade-offs trong thiết kế kiến trúc AI platform của bạn. Bạn đã cân bằng giữa performance, reliability, và maintainability như thế nào?**

   - **Performance vs. Reliability:** Kiến trúc hybrid Local + Kaggle GPU cho phép tận dụng GPU mạnh (T4/P100) cho model inference mà không cần đầu tư hardware, nhưng phụ thuộc vào ngrok tunnel nên latency cao hơn (~200-500ms overhead). Để giữ reliability, API Gateway (`api-gateway/main.py`) implement cơ chế `ALLOW_LLM_FALLBACK=true` — khi tunnel ngrok bị ngắt, gateway trả về fallback response thay vì crash, đảm bảo SLA cho downstream consumers.
   - **Reliability vs. Maintainability:** Sử dụng Docker Compose để orchestrate 8 services (Kafka, Zookeeper, Prefect, Qdrant, Redis, Prometheus, Grafana, API Gateway) giúp setup reproducible trên bất kỳ máy nào bằng `docker compose up -d`. Trade-off là file `docker-compose.yml` cần maintain env vars qua `.env` file, nhưng `.env.example` document rõ ràng tất cả biến cần thiết.
   - **Performance vs. Maintainability:** Kafka consumer trong `kafka_to_delta.py` dùng `consumer_timeout_ms=5000` (auto-stop sau 5s idle) thay vì long-running consumer, giúp script dễ chạy và debug hơn nhưng không phải real-time streaming. Delta Lake lưu bằng Parquet format đơn giản thay vì full Delta protocol, giảm complexity nhưng vẫn giữ được columnar storage benefits.

2. **Trong kiến trúc hybrid (Local + Kaggle), bạn xử lý ngắt kết nối giữa local và Kaggle như thế nào? Có cơ chế fallback không?**

   Có, hệ thống implement **multi-layer fallback** tại mỗi integration point:

   - **API Gateway LLM Fallback** (`api-gateway/main.py`, dòng 58-69): Khi gọi vLLM qua ngrok tunnel bị timeout hoặc lỗi HTTP, gateway bắt `httpx.HTTPError` và trả về fallback response có nội dung mô tả rằng tunnel không khả dụng, kèm context hits từ Qdrant. Client vẫn nhận 200 OK thay vì 502, giữ được trải nghiệm người dùng. Cơ chế này được bật/tắt qua `ALLOW_LLM_FALLBACK` env var.
   - **Embedding Fallback** (`scripts/05_embed_to_qdrant.py`, dòng 40-42): Khi embedding service trên Kaggle không khả dụng, script sử dụng deterministic fallback: hash SHA-256 của text rồi normalize thành vector 384 chiều. Vector này không có semantic meaning thật nhưng đảm bảo Qdrant collection luôn có data để demo.
   - **Timeout Configuration:** `LLM_TIMEOUT_SECONDS` có thể điều chỉnh qua `.env` (mặc định 45s) để phù hợp với ngrok latency thực tế. Khi tunnel ổn định, tăng timeout để chờ inference; khi tunnel bất ổn, giảm timeout và dựa vào fallback.

3. **Giải thích cách event-driven architecture với Kafka giúp decouple các components trong AI platform của bạn.**

   Kafka đóng vai trò **message broker trung tâm** qua topic `data.raw`, tạo loose coupling giữa 3 tầng:

   - **Producer** (`scripts/01_ingest_to_kafka.py`): Gửi raw documents vào topic `data.raw` với JSON serialization. Producer không cần biết ai sẽ consume data — nó chỉ cần Kafka broker tại `localhost:9092` khả dụng.
   - **Consumer/Processor** (`prefect/flows/kafka_to_delta.py`): Prefect flow consume từ `data.raw` với consumer group `lab28-prefect`, xử lý batch và lưu thành Parquet files trong Delta Lake. Consumer có thể chạy độc lập, restart bất kỳ lúc nào mà không mất data nhờ `auto_offset_reset="earliest"`.
   - **Downstream Services**: Qdrant vector store và Redis feature store được populate từ Delta Lake output, không phụ thuộc trực tiếp vào Kafka.

   **Lợi ích decoupling:**
   - Producer và Consumer có thể scale độc lập (thêm consumer instances nếu cần throughput cao hơn).
   - Kafka lưu trữ messages cho đến khi consumer xác nhận, nên nếu Prefect worker bị crash, data không bị mất và sẽ được xử lý khi worker restart.
   - Listener config với `PLAINTEXT://kafka:29092` cho container-to-container và `PLAINTEXT_HOST://localhost:9092` cho host access, cho phép cả Docker services và local scripts kết nối cùng Kafka cluster.

4. **Bạn đã implement observability như thế nào? Logs, metrics, và traces được thu thập và visualized ra sao?**

   Observability được implement theo **three pillars** model:

   - **Metrics (Prometheus + Grafana):**
     - API Gateway sử dụng `prometheus_fastapi_instrumentator` (Integration 9) để tự động expose metrics tại `/metrics` endpoint: `http_requests_total`, `http_request_duration_seconds`, `http_request_size_bytes`, v.v.
     - Prometheus scrape 3 targets mỗi 15 giây (`monitoring/prometheus.yml`): `api-gateway:8000`, `kafka:9092`, `prefect-orion:4200`.
     - Grafana dashboard "API Gateway Metrics" (UID: `lab28-dash`) hiển thị biểu đồ HTTP Requests Total theo thời gian thực, phân loại theo endpoint (`/api/v1/chat`, `/health`, `/docs`) và HTTP method.
     - Data source Prometheus được cấu hình tại `http://prometheus:9090` trong Grafana.

   - **Logs:**
     - Tất cả services trong Docker Compose ghi log ra stdout/stderr, có thể xem qua `docker compose logs <service>`.
     - Prefect flows có `log_prints=True`, tự động capture print statements thành Prefect log entries hiển thị trong Prefect UI tại `localhost:4200`.
     - Các scripts Python đều print checkpoint messages (e.g., "Consumed 4 records from Kafka", "Saved 4 records to Delta Lake") để trace data flow.

   - **Traces (LangSmith):**
     - API Gateway hỗ trợ LangChain tracing qua env vars `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT=lab28-platform`, và `LANGCHAIN_TRACING_V2`. Khi enabled, mỗi LLM inference request được trace end-to-end trên LangSmith dashboard.

5. **Nếu một service trong stack (ví dụ: Qdrant hoặc Kafka) bị crash, hệ thống của bạn sẽ xử lý như thế nào? Có graceful degradation không?**

   Có, hệ thống implement graceful degradation tại nhiều tầng:

   - **Qdrant crash:** Hàm `search_context()` trong `api-gateway/main.py` (dòng 24-35) wrap Qdrant call trong try/except, bắt `httpx.HTTPError`. Nếu Qdrant không phản hồi hoặc trả lỗi, function return empty list `[]` thay vì crash. API Gateway vẫn hoạt động bình thường — chỉ là LLM inference sẽ không có context từ vector search, nhưng user vẫn nhận được response.

   - **Kafka crash:** Kafka consumer trong `kafka_to_delta.py` có `consumer_timeout_ms=5000`, nên nếu Kafka broker không available, consumer sẽ timeout và flow kết thúc gracefully thay vì hang forever. Data đã produce vào Kafka được persist trên disk, nên khi Kafka restart, consumer có thể replay từ last committed offset.

   - **vLLM/ngrok crash:** Đây là failure case phổ biến nhất. API Gateway xử lý bằng fallback response (câu 2), trả về thông báo rằng tunnel unavailable kèm context hits. Health endpoint `/health` vẫn trả `{"status":"ok"}` — service availability không bị ảnh hưởng bởi LLM backend.

   - **Redis crash:** Script `03_delta_to_feast.py` sẽ fail nếu Redis down, nhưng điều này không ảnh hưởng đến API Gateway hay Kafka pipeline — chỉ feature serving bị gián đoạn. Smoke test `test_feast_redis_has_features` sẽ phát hiện Redis failure sớm.

   - **Toàn bộ stack restart:** `docker compose down -v && docker compose up -d` khôi phục toàn bộ services. Qdrant data persist qua Docker volume `qdrant_data`, Prefect state qua `prefect_data`. Kafka và Redis data sẽ cần re-ingest bằng cách chạy lại scripts theo thứ tự trong README.

## Câu Hỏi Thêm?
Liên hệ giảng viên qua LMS hoặc office hours.
