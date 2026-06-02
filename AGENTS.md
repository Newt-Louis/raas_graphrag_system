# AGENTS.md

Hướng dẫn này áp dụng cho toàn bộ repository `raas_graphrag_system`. Mỗi lần Codex làm việc trong dự án này, hãy đọc file này trước khi suy luận về kiến trúc, đặt tên API, thiết kế UI, hoặc thêm chức năng.

## Tổng Quan Sản Phẩm

Dự án này là một hệ thống **GraphRAG-as-a-Service**, không phải một ứng dụng GraphRAG đơn lẻ cho một sản phẩm cụ thể.

Hệ thống cung cấp nền tảng GraphRAG đa tenant cho nhiều phần mềm bên ngoài tích hợp. Mỗi phần mềm/khách hàng có tài liệu, cấu hình model, cấu hình giao diện chat, khóa API, vòng đời tài liệu, quota, và ngữ cảnh truy vấn riêng. Khi thiết kế tính năng mới, luôn ưu tiên ranh giới tenant, bảo mật dữ liệu, khả năng mở rộng API, khả năng vận hành nhiều provider/model, và khả năng nhúng giao diện vào sản phẩm bên thứ ba.

Ba nhóm trải nghiệm chính:

1. **Chat API + embeddable chat UI cho người dùng cuối của khách hàng**
   - Cho phép người dùng cuối chat với hệ thống dựa trên bộ tài liệu mà phần mềm/khách hàng đã cung cấp.
   - UI chat do hệ thống này cung cấp để nhúng vào sản phẩm bên ngoài, ví dụ iframe/script/widget.
   - Chat phải được ràng buộc theo tenant/app/document collection, không được rò rỉ ngữ cảnh giữa các khách hàng.

2. **Document Admin API + UI cho admin của khách hàng**
   - Cho phép admin bên khách hàng upload, quản lý, cập nhật, xóa, re-index, xem trạng thái xử lý và vòng đời tài liệu.
   - Sau khi tài liệu được nạp, hệ thống thực hiện pipeline GraphRAG: parse, chunk, trích xuất entities/relations, embed, lưu graph/vector metadata, và sẵn sàng cho API chat.
   - UI admin của khách hàng cần có ít nhất hai tab/phần lớn:
     - Quản lý tài liệu.
     - Quản lý giao diện chat embeddable: vị trí, kích thước, màu sắc, popup, hành vi hiển thị, kiểu khung chat, v.v.

3. **Platform Admin UI cho người vận hành hệ thống của ta**
   - Quản lý tenant/app đang sử dụng hệ thống.
   - Quản lý provider/model, API key, endpoint, pool xoay vòng, quota, trạng thái tenant/app, và cảnh báo vận hành.
   - Đây là trang quản trị nội bộ của hệ thống GraphRAG-as-a-Service, khác với UI admin của khách hàng.

## Hiện Trạng Source

Repo hiện tại đã tách rõ hơn thành các lõi nền tảng:

- Backend FastAPI:
  - Entry point: `app/main.py`.
  - Cấu hình: `app/core/config.py`.
  - Router hiện có được auto-include từ `app/api/v1/*.py` với prefix `/api/v1`.
  - API hiện có: `app/api/v1/home.py`, `app/api/v1/ingest.py`, `app/api/v1/chat.py`, `app/api/v1/embed.py`, `app/api/v1/documents.py`, `app/api/v1/visualize.py`, `app/api/v1/platform_ai.py`.
  - `home.py` và các route `feature1/feature2` trong embed vẫn là placeholder; khi mở rộng, ưu tiên tên domain thật.
- AI Gateway:
  - Thư mục: `app/ai_gateway/`.
  - Đã có `AIGateway`, `ModelProfile`, `GatewayRequestContext`, `UsageRecord`; LLM dùng `BaseRotator`/`KeyPool`/`LLMRotator`, còn embedding Gemini dùng adapter chuyên biệt `app/ai_gateway/embedding_gemini.py`.
  - Đây là lõi cần hoàn thiện trước để có model embedding/LLM thật phục vụ test GraphRAG.
- GraphRAG:
  - Thư mục: `app/graphrag/`.
  - `GraphRAGAIClient` đã tồn tại để GraphRAG gọi embedding/LLM qua AI Gateway.
  - `app/graphrag/llama_index/` chứa QueryEngine retrieval-only dùng chung. Giai đoạn 1 bắt buộc dùng LlamaIndex làm orchestration spine cho vector/graph ingestion và retrieval; synthesis model vẫn gọi trực tiếp qua AI Gateway.
  - `app/graphrag/vector_database/` nhận chunk/query, gọi Gemini embedding trực tiếp qua `GraphRAGAIClient`/AI Gateway, rồi dùng adapter chính thức `llama_index.vector_stores.lancedb.LanceDBVectorStore` và QueryEngine retrieval-only để lưu/query LanceDB. Module này chưa gọi LLM synthesis.
  - `app/graphrag/graph_database/` dùng `PropertyGraphIndex` và một `PropertyGraphStore` bridge trên Kuzu để giữ đầy đủ tenant/app/document metadata. Graph retrieval đi qua QueryEngine retrieval-only; visualization/stats đi qua bridge structured query. Community detection/summary vẫn chưa có.
- Services:
  - `app/services/ingestion/`: document parsing/chunking/deduplication/fanout records.
  - `app/services/vector/`: embedding local hashing cho dev/test, LanceDB vector store, in-memory vector store cho unit test.
  - `app/services/retrieval/`: retrieval orchestrator lấy vector candidates trước, rồi dùng Kuzu structure/semantic graph để mở rộng context nếu graph store được cấu hình.
- Database/model:
  - `app/db/base.py`, `app/db/session.py`: SQLAlchemy base/session.
  - `app/models/platform.py`: platform users, tenants, customer apps.
  - `app/models/documents.py`: documents và ingestion jobs.
  - `app/models/ai_gateway.py`: provider, API key, model catalog, LLM rotation pools/profiles, embedding profiles, usage events.
  - Chưa thấy migration Alembic hoàn chỉnh tương ứng với toàn bộ model mới; nếu thêm/sửa DB schema thì cần xử lý migration thay vì chỉ sửa model.
- Core:
  - `app/core/config.py` đã có config DB, path runtime, LanceDB/vector, embedding local, CORS.
  - `app/core/lifespan.py`, `logging.py`, `security.py`, `exceptions.py` hiện còn rỗng hoặc rất nhẹ; không giả định chúng đã có middleware/auth/logging production.
- Frontend Vue/Vite:
  - Thư mục: `ui/`.
  - Entry point: `ui/src/main.ts`.
  - Root component: `ui/src/App.vue`.
  - Router: `ui/src/router/index.ts`.
  - Theme variables: `ui/src/styles/theme.css`.
  - Embed config composable: `ui/src/composables/useEmbedConfig.ts`.
- Storage/runtime:
  - PostgreSQL và Redis trong `docker-compose.yml`.
  - Kuzu graph DB path: `data/kuzu/graph.db`.
  - LanceDB path: `data/lancedb`.
  - Data/documents, graph DB, vector DB, cache, logs là runtime data và không nên commit.
- Static frontend build:
  - `ui/vite.config.ts` build Vue ra `app/static`.
  - FastAPI mount `/assets` và fallback SPA từ `app/static/index.html`.

Lưu ý quan trọng: các tên route cũ như `feature1`, `feature2`, hoặc code demo trong `home.py` chỉ là placeholder. Khi mở rộng sản phẩm, ưu tiên đặt tên theo domain thật: `chat`, `documents`, `tenants`, `apps`, `platform`, `admin`, `embed`, `widget`, `ingestion`, `ai-gateway`, `model-profiles`.

## Ưu Tiên Kiến Trúc Hiện Tại

Giai đoạn hiện tại ưu tiên hoàn thiện **lõi API xoay vòng model** trước khi dựng sâu GraphRAG. Lý do: nếu chưa có cơ chế gọi embedding/LLM thật, kiểm tra GraphRAG sẽ chỉ là kiểm tra giả lập và không phản ánh được quota, lỗi provider, model dimension, latency, và fallback runtime.

Thứ tự ưu tiên hợp lý:

1. Hoàn thiện AI Gateway cho hai capability tách biệt: `embedding` và `llm`.
2. Hoàn thiện Platform Admin/API để cấu hình provider, model, API key, endpoint, pool, lock, quota, usage, và test call.
3. Nối ingestion/query embedding vào embedding gateway theo profile đúng chiều vector.
4. Nối chat synthesis/rerank/tool/structured output vào LLM gateway.
5. Sau khi có gateway test được, mới mở rộng GraphRAG engine, graph retrieval, reranking, synthesis, citation, và hybrid retrieval.

## Hướng Kiến Trúc Cần Giữ

Thiết kế theo GraphRAG-as-a-Service đa tenant:

- Mỗi request quan trọng cần có ngữ cảnh tenant/app rõ ràng, ví dụ `tenant_id`, `app_id`, API key, JWT claim, hoặc scoped route.
- Không viết logic mặc định như thể chỉ có một bộ tài liệu toàn cục.
- Không trộn data của platform admin, customer admin, và end-user chat.
- API phải có ranh giới quyền:
  - Platform operator: quản lý tenant/app/provider/model/API key/pool/quota/lock.
  - Customer admin: quản lý tài liệu và cấu hình widget của app mình.
  - End user: chỉ chat với ngữ cảnh được phép của app/tenant đó.
- GraphRAG pipeline nên tách service:
  - Upload/document lifecycle.
  - Parsing/chunking.
  - Entity/relation extraction.
  - Embedding/vector indexing.
  - Graph storage/query.
  - Retrieval/reranking/synthesis.
  - Job status/progress.
- Business logic nên nằm trong `app/services/`, persistence trong `app/db/`/`app/repositories/`, API schema/model riêng khi dự án lớn hơn.

## Kiến Trúc Lớp Hệ Thống

Từ giai đoạn này, hệ thống được phát triển theo ranh giới lớp rõ ràng:

- `app/core/`: lớp nền tảng của app. Chỉ chứa config, logging, security, middleware, exception mapping, lifespan, dependency chung. Không đặt logic xoay vòng provider, GraphRAG retrieval, hay nghiệp vụ tenant/chat/document vào core.
- `app/ai_gateway/`: lớp điều phối AI provider/model/key. Trả lời các câu hỏi: dùng provider nào, dùng key nào, key còn quota không, có bị rate limit không, lỗi này retry/xoay/dừng, ghi usage ra sao, endpoint/model nào bị khóa. Lớp này không quyết định tenant có quyền chat hay không và không dựng prompt GraphRAG.
- `app/graphrag/`: lớp GraphRAG engine/pipeline. Trả lời các câu hỏi: cần embedding văn bản nào, lấy context nào từ vector/graph, prompt cần lắp ghép thế nào, cần LLM sinh câu trả lời thế nào. Lớp này gọi AI Gateway để thực thi embedding/LLM, nhưng không tự chọn key, tự xử lý quota, hay tự retry provider.
- `app/services/`: lớp nghiệp vụ sản phẩm. Trả lời các câu hỏi: tenant/app nào đang gọi, session nào, user/admin có quyền không, lưu lịch sử chat ở đâu, document lifecycle đi qua các trạng thái nào, API nên trả response/schema nào. Services có thể gọi GraphRAG, AI Gateway, repositories, và core dependencies.
- `app/repositories/` hoặc `app/db/`: lớp persistence. Chỉ đọc/ghi database, cache, vector/graph metadata theo interface rõ ràng. Không chứa workflow nghiệp vụ dài.
- `app/api/v1/`: lớp HTTP adapter. Router nên mỏng: validate request, lấy dependency/auth context, gọi service, trả schema. Không đặt logic xoay key, retrieval, prompt, document pipeline trực tiếp trong router nếu logic đó bắt đầu lớn.

Luôn giữ chiều phụ thuộc rõ để tránh trộn trách nhiệm: API -> Services -> GraphRAG/AI Gateway/Repositories -> Core utilities. GraphRAG có thể dùng AI Gateway để gọi model; AI Gateway không phụ thuộc ngược vào GraphRAG hoặc Services.

### LlamaIndex Là Xương Sống GraphRAG

- LlamaIndex là dependency kiến trúc bắt buộc cho phần GraphRAG, không phải package cài sẵn để dành.
- Vector database:
  - Dùng adapter chính thức `LanceDBVectorStore` của LlamaIndex cho LanceDB.
  - Embedding vẫn do `GraphRAGAIClient`/AI Gateway gọi trực tiếp rồi truyền vector đã tính sẵn vào LlamaIndex node; không dùng `llama-index-embeddings-*` làm runtime model gateway.
  - Retrieval phải đi qua LlamaIndex QueryEngine/retriever contract và luôn filter tenant/app/collection.
- Graph database:
  - Ingestion structure graph và semantic graph phải đi qua `PropertyGraphIndex`.
  - Kuzu dùng `KuzuGraphStore` triển khai `PropertyGraphStore` bridge riêng vì adapter mặc định của LlamaIndex không giữ đủ tenant/app/document metadata cần cho GraphRAG-as-a-Service.
  - Retrieval graph phải đi qua QueryEngine/retriever contract. Structured query chỉ nằm bên trong bridge cho visualization, stats, delete và traversal implementation.
- Chunking:
  - `app/services/ingestion/chunking.py` (`DocumentChunker`) dùng node parser LlamaIndex: `sliding_window`->`SentenceSplitter`, `parent_child`->`HierarchicalNodeParser`, `semantic`->`SemanticSplitterNodeParser`. Tokenizer truyền `cl100k_base` để khớp `_token_count`.
  - Mỗi structural section (đã tách theo trang/slide/sheet/heading) là một LlamaIndex `Document` riêng nên chunk không vượt ranh giới trang và thừa hưởng đúng `source_element_ids`.
  - GIỮ NGUYÊN hợp đồng đầu ra `DocumentChunker.chunk()/chunk_async()->list[DocumentChunk]` với provenance (`source_element_ids`, `parent_chunk_id`, `is_embeddable`, `chunk_role`, page/boundary) để graph/vector phía sau không phải đổi. Khi sửa chunking, không phá hợp đồng này.
  - Semantic chunking cắt theo `semantic_breakpoint_percentile` (mặc định 95) của phân phối khoảng cách, không phải cosine threshold thô. `semantic_similarity_threshold` cũ giữ lại chỉ để tương thích form, chunker không dùng.
- Embedding cho LlamaIndex node parser (SemanticSplitter) đi qua `app/graphrag/llama_index/embedding.py::GatewayEmbedding` — một `BaseEmbedding` bọc embedding gateway nội bộ (google-genai SDK). KHÔNG dùng `llama-index-embeddings-*`. `GatewayEmbedding` bridge async->sync; chunker chạy SemanticSplitter trong `asyncio.to_thread`.
- Chat retrieval (Router + Hybrid + Synthesis):
  - `app/services/retrieval/graphrag.py::GraphRAGRetrievalService` luôn chạy vector retrieval (grounding/citation), rồi mở rộng graph theo chunk. Thêm bước **router** dùng `LLMSingleSelector` (lõi của `RouterRetriever`) để LLM quyết định câu hỏi có cần graph traversal không.
  - Nếu cần graph: chạy LlamaIndex `TextToCypherRetriever` trên `KuzuGraphStore` (`app/graphrag/llama_index/graph_text2cypher.py`). Schema cho text2cypher lấy từ `KuzuGraphStore.get_schema_str()` (node tables + props + rel endpoints). Prompt nhúng scope tenant/app/collection. Có guardrail `read_only_cypher_validator` chặn CREATE/MERGE/SET/DELETE/DETACH/DROP... — text2cypher CHỈ được đọc.
  - Toàn bộ nhánh graph-query gated theo `isinstance(graph_store, KuzuGraphStore)` + có `router_llm`, và bọc graceful: lỗi router/cypher KHÔNG được làm vỡ chat (fallback về vector + graph-expansion).
- Ngoại lệ cho phép import LlamaIndex LLM interface: được tạo `app/graphrag/llama_index/gateway_llm.py::GatewayLLM(CustomLLM)` bọc AI Gateway (rotation LiteLLM) **chỉ** để các engine điều phối/truy vấn của LlamaIndex (`LLMSingleSelector`/`RouterRetriever`, `TextToCypherRetriever`) gọi được LLM. Việc thực thi model vẫn qua AI Gateway nội bộ; mọi chỗ khác vẫn KHÔNG dùng `llama-index-llms-litellm` như lớp trung gian.
- LLM synthesis (sinh câu trả lời chat cuối) và embedding API vẫn gọi trực tiếp qua AI Gateway hiện hữu, không qua adapter LLM của LlamaIndex.
- Batching embedding: adapter `app/ai_gateway/embedding_gemini.py` gom nhiều `Content` vào một `embed_content` (sub-batch theo `batch_size`), mặc định cap `DEFAULT_EMBEDDING_BATCH_SIZE=100` khi profile không khai báo, và retry/backoff khi gặp 429/RESOURCE_EXHAUSTED/503. Số lần gọi API = `ceil(số_item/batch_size)`; semantic tốn hơn vì phải embed từng câu để dò ranh giới (bản chất thuật toán, không phải bug).
- Không thêm lại pipeline LanceDB/Kuzu chạy song song bên ngoài `app/graphrag/`. Các compatibility service cũ nếu còn tồn tại phải delegate vào adapter LlamaIndex.
- Giai đoạn sau:
  - TODO: dùng ChatEngine khi có persisted chat memory/history.
  - TODO: dùng Workflows để rẽ nhánh text, multimodal, graph traversal sâu, loop và parallel path trong FastAPI async.

## Ranh Giới AI Gateway

`app/ai_gateway/` là lõi hệ thống cần hoàn thiện đầu tiên để có thể nạp nhiều API key/model và test thật qua trang admin. Khi sửa lớp này, giữ các quy ước sau:

- AI Gateway chỉ nhận các `ModelProfile`/`KeyConfig` đã được service/repository nạp vào. Nếu key lưu trong DB thì phải decrypt trước khi đưa vào gateway; gateway không hard-code secret và không log secret.
- `AIGateway` là facade duy nhất cho GraphRAG/Services gọi model. Tránh để GraphRAG hoặc router gọi trực tiếp `litellm`, `EmbeddingRotator`, hoặc `LLMRotator` nếu không phải test cấp thấp.
- `BaseRotator`, `KeyPool` và `errors.py` chỉ phục vụ LLM qua LiteLLM: acquire key, classify error, retry same key, rotate key, cooldown, disable, abort/admin notify, và trả `RotationResult`.
- Phải tách 2 cơ chế runtime:
  - **Gemini embedding adapter**: dùng `app/ai_gateway/embedding_gemini.py` và package `google-genai`, chỉ hydrate đúng một Gemini profile/API key, không xoay key, không trộn provider/model. Embed document phải gửi `RETRIEVAL_DOCUMENT`; embed query phải gửi `RETRIEVAL_QUERY`. Model và dimension của index LanceDB phải giữ cố định.
  - **LLM AI API pool**: dùng `LLMRotator` qua LiteLLM cho sinh câu trả lời, synthesis, reranking LLM nếu có, tool/structured output nếu sau này cần. Quản lý generation params như temperature, max tokens, timeout, streaming/tool calling theo request/profile.
- Không trộn key embedding và key LLM trong cùng một pool. Một provider có thể có cả embedding và LLM key, nhưng runtime profile phải tách theo `capability`/`model_type`: `embedding` hoặc `llm`.
- DB model chỉ giữ `llm_rotation_pools` cho LLM. Embedding không có rotation pool; runtime đọc trực tiếp record `embedding_model_profiles` mới nhất theo `created_at`.
- Quota/usage cần được ghi theo tối thiểu: provider, key_id, model, capability, tenant/app nếu request có scope, endpoint, input/token count nếu có, latency, success/error verdict.
- Endpoint/model lock là chính sách của Platform Admin: admin có thể khóa provider, key, model, endpoint, capability, hoặc tenant/app mapping. Gateway phải tôn trọng lock trước khi acquire key.
- Nếu gặp lỗi cấu hình cần admin can thiệp, gateway phải nổi lên platform admin dashboard thay vì âm thầm retry vô hạn.
- `health_snapshot()` không được trả secret. Các API/debug endpoint tương lai cũng không được expose `api_key` hoặc `encrypted_api_key`.

## Ranh Giới GraphRAG

GraphRAG không phải nơi quản lý key/provider. GraphRAG chỉ nên nắm các quyết định liên quan chat với tài liệu:

- Tạo embedding cho document chunks và query bằng cách gọi embedding profile của AI Gateway.
- Đọc context từ LanceDB/vector store và Kuzu/graph store theo tenant/app/document scope.
- Lắp prompt/system instruction theo câu hỏi, retrieved context, chat history, policy của app, và citation/source metadata.
- Gọi LLM profile qua AI Gateway để sinh câu trả lời.
- Nếu không có context, document chưa ready, hoặc retrieval fail, trả trạng thái rõ ràng cho service để API không hallucinate.
- Prompt/retrieval/reranking/synthesis nằm trong `app/graphrag/` hoặc service GraphRAG chuyên biệt; không đưa vào AI Gateway.
- `app/graphrag/engine.py`, `ingestion_pipeline.py`, `query_pipeline.py` đã có wrapper tối thiểu cho graph ingestion/query/retrieval. Không ghi tài liệu như thể community detection, community summary hoặc reranking production đã hoàn chỉnh.

## Ranh Giới Services

Services là nơi biểu diễn nghiệp vụ GraphRAG-aaS và là lớp kết nối các hệ thống con:

- Xác định tenant/app/session/user/admin context từ API key, JWT claim, route scope, hoặc dependency.
- Kiểm tra quyền: platform operator, customer admin, end user.
- Quản lý document lifecycle: upload, parse, chunk, deduplicate, index, re-index, archive/delete, job status/progress.
- Quản lý chat session/history, audit log, rate limit theo tenant/app/end user nếu cần.
- Chọn model profile/capability được phép cho tenant/app rồi truyền danh sách key/model hợp lệ vào AI Gateway.
- Định nghĩa response API và lỗi domain rõ ràng cho frontend/API client.

## Vector Retrieval Và Hybrid Sau Này

Toàn bộ retrieval hiện đi qua MỘT đường duy nhất `GraphRAGRetrievalService`; đã bỏ đường hashing song song cũ:

- `app/services/retrieval/graphrag.py` có `GraphRAGRetrievalService` (async) + `GraphRAGRetrieval`: embed query qua embedding gateway thật, search LanceDB qua adapter LlamaIndex, rồi mở rộng grounded matches bằng Kuzu semantic/structure graph. Trả `vector_matches`, `graph_chunks`, `graph_entities`, `strategy` (`vector_only`/`vector_graph`/`vector_semantic_graph`/`no_context`), `embedding_model`, `usage`.
- Đây là điểm hứng retrieval dùng chung cho cả `ChatCompletionService` (answer synthesis) và các route debug `POST /api/v1/chat/retrieve`, `GET /api/v1/home`. Không tạo lại retriever riêng cho từng caller; mọi nơi gọi service này để không rơi về index hashing cục bộ.
- ĐÃ XÓA: `app/services/vector/` (`HashingTextEmbeddingService`, compat `LanceDBVectorStore`/`InMemoryVectorStore`) và `app/services/retrieval/orchestrator.py`/`factory.py`/`models.py`. Không khôi phục lại hashing embedding cho đường retrieval; mọi vector phải cùng embedding profile/dimension với index.
- `app/graphrag/vector_database/` là luồng GraphRAG-facing cho LanceDB với Gemini embedding thật: `GraphRAGVectorDatabasePipeline.ingest()` gọi AI Gateway Gemini adapter để embed document chunks rồi lưu vào LanceDB; `query()` embed query bằng cùng Gemini profile rồi tìm trong LanceDB và trả `VectorMatch` gồm `similarity`, `distance`, `document_id`, `chunk_id`, text và metadata. Luồng này dùng `settings.LANCEDB_PATH` và `settings.VECTOR_INDEX_TABLE` qua factory, không gọi LLM.
- LanceDB production được bọc bằng adapter chính thức LlamaIndex `LanceDBVectorStore`. Factory store dùng singleton cache theo process và connection lazy-init để tránh mở local DB lặp khi service được dựng theo request.
- Route `POST /api/v1/ingest` hiện parse/chunk tài liệu rồi gọi `app/graphrag/vector_database/` để embed qua một Gemini embedding profile hydrate từ PostgreSQL trước khi lưu LanceDB. Route `POST /api/v1/ingest/query` embed query qua cùng Gemini gateway rồi search LanceDB để trả cosine similarity, chưa gọi LLM synthesis.
- Khi chuyển sang embedding provider thật, ingest embedding và query embedding phải dùng cùng embedding profile hoặc profile tương thích dimension với index.
- Khi mở rộng hybrid/rerank, mở rộng `GraphRAGRetrievalService` để hợp nhất vector + graph và trả citation/source metadata. Không bẻ chat API sang gọi trực tiếp LanceDB/Kuzu.

## Platform Admin Và Cấu Hình AI

Platform Admin UI/API là nơi vận hành nội bộ của GraphRAG-as-a-Service. Khi bắt đầu thêm admin cho bộ xoay vòng API, ưu tiên các năng lực sau:

- Quản lý provider/model catalog theo `capability`: `embedding` và `llm`.
- Quản lý encrypted API keys, trạng thái active/cooldown/disabled, quota, endpoint/model lock, allowed tenant/app mapping.
- Quản lý LLM rotation pools theo platform/tenant/app; embedding dùng trực tiếp profile Gemini mới nhất và không có rotation pool.
- Xem usage, latency, success/fail, verdict/reason, key health snapshot, và cảnh báo cần admin xử lý.
- Test call riêng cho embedding và LLM để xác minh key/model trước khi dùng cho ingestion/chat.
- Cấu hình default model profile cho ingestion embedding, query embedding, chat synthesis, và các tác vụ phụ như rerank nếu có.

Customer Admin UI không được quản lý provider key nội bộ của platform. Customer Admin chỉ quản lý tài liệu, ingestion status, và widget/chat config trong tenant/app của họ.

Hiện trạng Platform Admin AI UI:

- `ui/src/views/PlatformAdminView.vue` chỉ là container/layout cho màn hình quản trị AI nội bộ; các page con nằm trong `ui/src/pages/admin_system/`.
- `ui/src/pages/admin_system/ProvidersPage.vue` quản lý bảng `ai_providers` và gọi API thật dưới `/api/v1/platform/ai/providers`.
- `ui/src/pages/admin_system/ModelProfilesPage.vue` là trang quản lý LLM model profile hiện tại; không dựng form riêng để admin tự tạo pool runtime thủ công trên UI nếu chưa có thiết kế rõ.
- Raw provider API key phải lưu qua bảng `ai_api_keys` bằng backend API, backend hash key vào `key_hash`, encrypt key vào `encrypted_api_key`, và frontend chỉ được nhận preview đã mask.
- Không nhập raw API key vào `llm_model_profiles.api_key_id`. Cột `api_key_id` trong `llm_model_profiles` là khóa ngoại tới `ai_api_keys.id`; `provider_id` là khóa ngoại tới `ai_providers.id`.
- Từ migration `202605310001`, bảng `embedding_rotation_pools` đã bị xóa. `embedding_model_profiles` là cấu hình trực tiếp cho Gemini embedding; record mới nhất theo `created_at` được dùng mặc định. `llm_rotation_pools` vẫn là runtime rows cho LLM.
- `current_position` trong bảng pool là marker 0/1 cho biết dòng runtime nào đang tới lượt gọi tiếp theo; vòng xoay đi theo `rotation_order`.
- Redis runtime sau này hydrate từ các bảng `*_rotation_pools` join sang `*_model_profiles`. Khi cooldown/quota hết hạn hoặc Redis bị flush/restart, worker/lifespan/service cần rehydrate hoặc reconcile Redis từ PostgreSQL theo bảng pool runtime.
- `status` trên danh sách model profile/API key/provider chỉ là trạng thái vận hành để hiển thị active/disabled/locked/cooldown; thao tác đổi trạng thái phải đi qua nút action và endpoint backend, không biến status thành ô chọn tự do trong bảng.

## Backend Quy Ước

- Framework hiện tại: FastAPI + Pydantic Settings + SQLAlchemy.
- Cấu hình mới nên thêm vào `app/core/config.py` và `.env.example`; không hard-code secret/model key.
- Không commit `.env`, document upload, DB files, vector index, graph DB, cache, logs, hoặc `__pycache__`.
- Nếu thêm API versioned, ưu tiên `app/api/v1/...`; hiện `app/main.py` auto-include router từ `app/api/v1/*.py`.
- Router prefix phải bắt đầu bằng `/`. Tránh include trùng router theo cả cách manual và auto.
- Dùng response/request schema rõ ràng cho API public; tránh nhận tham số quan trọng bằng query string tùy tiện nếu body/schema phù hợp hơn.
- API chat public không nên nhận raw `file_path` từ client. File path nội bộ phải được quản lý bởi document service.
- Khi thêm/sửa SQLAlchemy model, cập nhật migration Alembic hoặc ghi rõ migration chưa có. Không chỉ sửa model rồi coi như DB đã sẵn sàng.
- Khi cần chạy backend local:
  - `uvicorn app.main:app --reload`
- Khi cần hạ tầng local:
  - `docker compose up -d`

## Frontend Quy Ước

- Frontend hiện dùng Vue + Vite + Pinia + Vue Router.
- `ui/vite.config.ts` proxy `/api` và `/embed` về backend `http://localhost:8000`.
- Build frontend bằng:
  - `cd ui && npm run build`
- Chạy dev server bằng:
  - `cd ui && npm run dev`
- UI cần phân biệt rõ ba khu vực:
  - Platform Admin UI nội bộ.
  - Customer Admin UI cho document lifecycle và chat widget builder.
  - Embeddable Chat UI cho end user.
- Phần Platform Admin cho AI Gateway cần tách màn hình/luồng cho embedding profiles và LLM profiles.
- Chat widget builder cần lưu cấu hình theo tenant/app, không chỉ apply theme client-side tạm thời.
- Embed UI phải thân thiện với iframe/script nhúng: kích thước ổn định, theming qua config, postMessage có validate origin khi có auth/security thật.

## API Domain Đề Xuất

Khi thay placeholder, ưu tiên các namespace sau:

- `/api/v1/platform/...` cho admin nội bộ của hệ thống.
- `/api/v1/platform/ai/...` hoặc `/api/v1/ai-gateway/...` cho provider/model/key/pool/test-call/usage nội bộ.
- `/api/v1/apps/...` hoặc `/api/v1/tenants/...` cho đăng ký và cấu hình phần mềm khách hàng.
- `/api/v1/documents/...` cho upload, lifecycle, status, re-index.
- `/api/v1/chat/...` cho query/chat completion có ngữ cảnh tenant/app.
- `/api/v1/widget-config/...` cho cấu hình giao diện chat.
- `/embed/chat/...` cho giao diện chat embeddable.
- `/admin/...` hoặc route SPA tương ứng cho UI quản trị.

Đây chỉ là định hướng; nếu source đã có chuẩn mới trong tương lai, ưu tiên chuẩn hiện hữu hơn file này.

## Data Và Storage

- PostgreSQL: metadata hệ thống, tenant/app, users/admins, API keys, provider/model catalog, rotation pools/profiles, usage events, document metadata, job status, widget config, audit log.
- Kuzu: graph entities/relations phục vụ GraphRAG.
- LanceDB: vector embeddings/chunks/retrieval index.
- Redis: cache, queue/job coordination, rate limit, session tạm thời nếu cần.
- `data/` là runtime data, không commit.
- Mỗi bản ghi document/chunk/entity/vector/usage nên có tenant/app/document hoặc endpoint scope rõ ràng khi phù hợp.

## Bảo Mật Và Tích Hợp

- API key/JWT phải được hash/lưu an toàn khi đi vào production; không log secret.
- API key provider phải được mã hóa khi lưu DB. Chỉ decrypt ở service/repository trước khi đưa vào `KeyConfig`.
- Không trả `api_key`, `encrypted_api_key`, hoặc secret trong health snapshot, API response, log, fixture, hoặc AGENTS.md.
- CORS hiện đang mở `["*"]` để tiện embed/dev. Khi làm production, cần scoped origins theo tenant/app.
- Embed/postMessage phải tính tới validate origin, allowed domains, và không tin raw event data.
- Admin của khách hàng chỉ được xem/sửa tài liệu và widget config của app/tenant mình.
- End-user chat API cần rate limit, audit, và guardrails phù hợp vì đây là API public-facing.

## Chat/GraphRAG Behavior

- Chat response nên dựa trên retrieved context từ tài liệu của đúng tenant/app.
- Nếu không có ngữ cảnh, tài liệu chưa sẵn sàng, hoặc model gateway không có profile/key khả dụng, API nên trả trạng thái/lỗi rõ ràng thay vì hallucinate.
- Nên lưu citation/source metadata để UI có thể hiển thị nguồn.
- Document lifecycle cần có trạng thái như uploaded, parsing, indexing, ready, failed, archived/deleted.
- Pipeline nên idempotent ở các bước để có thể retry job.

## Kiểm Tra Và Chất Lượng

Test hiện có dùng `unittest` trong thư mục `test/`.

Các lệnh kiểm tra có sẵn/hợp lý:

- Backend unit tests:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s test`
- Frontend type check/build:
  - `cd ui && npm run build`
- Backend smoke run:
  - `uvicorn app.main:app --reload`
- Hạ tầng local:
  - `docker compose up -d`

Khi thêm logic có rủi ro, thêm test tương ứng trong `test/`. Các test AI Gateway nên ưu tiên fake/mock rotator hoặc test logic pool/classification trước; chỉ chạy provider thật khi có cấu hình rõ và không làm lộ secret.

Nếu thêm tool mới như pytest, ruff, alembic migrations, hay task queue, cập nhật file này và README/script liên quan.

## Quy Ước Làm Việc Cho Codex

- Luôn coi đây là sản phẩm platform/API-first, không phải demo chatbot đơn tenant.
- Trước khi sửa kiến trúc, quét source hiện tại và giữ pattern đang có nếu hợp lý.
- Không overwrite thay đổi người dùng đã làm.
- Khi tạo file/chức năng mới, đặt tên theo domain GraphRAG-aaS thật thay vì `feature1/feature2`.
- Khi sửa frontend, đảm bảo route/component tồn tại thật và build được.
- Khi sửa backend, đảm bảo router prefix/path hợp lệ; tránh lỗi path thiếu dấu `/`.
- Không đưa secret vào code, log, fixture, hoặc AGENTS.md.
- Nếu yêu cầu liên quan OpenAI/API/model mới nhất, phải kiểm tra tài liệu chính thức trước khi kết luận.

## Cập Nhật Trạng Thái Session 01/06/2026

Mục này ghi lại trạng thái mới nhất sau phiên làm việc ngày 29/05/2026. Khi tiếp tục dự án, ưu tiên đọc mục này cùng các quy ước kiến trúc ở trên.

### Đã Hoàn Thành

- Platform Admin AI:
  - UI `/platform` đã có luồng quản lý provider và model profiles trong `ui/src/pages/admin_system/`.
  - Model profile UI đã tách capability `llm` và `embedding`.
  - API key là input raw key, không còn là select trong form profile.
  - Provider/model select hiển thị `display_name`/label nhưng gửi `id` về backend để lưu DB.
  - Backend cho phép cùng một raw API key được dùng cho nhiều loại model/capability; đã bỏ ràng buộc unique tuyệt đối trên `ai_api_keys.key_hash` và thêm migration `202605280001_allow_duplicate_ai_api_key_hash.py`.
  - Embedding profile không cần `max_output_tokens`; các thông tin như MRL dimension/MTEB score nếu cần nên để trong `extra_parameters`.
- AI Gateway:
  - Có runtime hydrate embedding gateway từ PostgreSQL qua `app/services/ai_gateway_runtime.py`.
  - Có runtime hydrate LLM gateway từ PostgreSQL qua `build_llm_gateway()`. Runtime facade `runtime-llm-pool` chỉ dùng để xoay key/profile; lời gọi thành công vẫn ghi UUID masterdata từ `llm_model_profiles.id`.
  - Embedding gateway hydrate trực tiếp record `embedding_model_profiles` mới nhất theo `created_at`, chỉ dùng đúng một Gemini API key. `KeyConfig.model_profile_id`, `RotationResult.profile_id`, usage event và vector record ghi vào LanceDB dùng UUID masterdata này.
  - `BaseRotator` không còn trả lỗi mơ hồ kiểu `Vượt quá max_attempts=...`; khi hết lượt thử sẽ trả lỗi cuối của provider/model/key đã được phân loại và redact secret.
  - `errors.py` đã bổ sung heuristic cho các lỗi 400/401/404 bị LiteLLM bọc trong `APIError` để không retry/rotate vô ích.
- Ingestion + Vector DB:
  - Route `POST /api/v1/ingest` parse/chunk tài liệu, gọi embedding gateway thật, lưu vector đã tính vào LanceDB.
  - Route `POST /api/v1/ingest/query` embed query bằng cùng embedding gateway rồi search LanceDB và trả similarity/distance/chunk metadata, có nối graph context nếu Kuzu có dữ liệu.
  - `app/graphrag/vector_database/` có pipeline GraphRAG-facing cho ingest/query LanceDB qua `GraphRAGAIClient`.
  - Adapter `google-genai` phải đóng gói mỗi chunk thành một `types.Content` riêng trước khi gọi `embed_content()`. Riêng `gemini-embedding-2`, truyền thẳng `list[str]` làm SDK gom nhiều chuỗi thành nhiều part của một content và chỉ trả một vector.
- Document lifecycle:
  - Migration `202605310002_document_registry_lifecycle.py` cho phép `documents.tenant_id`/`app_id` nullable trong giai đoạn đầu và thêm unique constraint `uq_documents_filename`.
  - `POST /api/v1/ingest` kiểm tra filename đầy đủ gồm extension trước khi lưu file. Nếu tên đã tồn tại trong PostgreSQL, route trả `409` và không parse/embed/index lại.
  - Sau parse/chunk, route lưu document vào PostgreSQL ở trạng thái `indexing`, chuyển sang `ready` sau khi LanceDB/Kuzu hoàn tất hoặc giữ `failed` nếu index lỗi.
  - `GET /api/v1/documents` trả danh sách registry. `DELETE /api/v1/documents/{document_id}` xóa record PostgreSQL, file upload, vector LanceDB theo `document_id` và graph Kuzu theo scope nội bộ.
  - `ui/src/views/DocumentAdminView.vue` hiển thị danh sách tài liệu PostgreSQL và action delete. Tiến trình upload tạm thời nằm trong modal upload, không còn chiếm panel chính.
- Graph DB/Kuzu:
  - Refactor 01/06/2026: LlamaIndex đã được nhập vào làm xương sống thay cho pipeline Kuzu/LanceDB tự gọi trực tiếp. Kuzu ingestion dùng `PropertyGraphIndex`; Kuzu bridge triển khai `PropertyGraphStore`; graph/vector retrieval dùng QueryEngine retrieval-only. AI Gateway vẫn gọi model trực tiếp.
  - Đã dựng `app/graphrag/graph_database/` với `KuzuGraphStore`, schema Document/Element/Chunk và relations `HAS_ELEMENT`, `HAS_CHUNK`, `DERIVED_FROM`, `NEXT_CHUNK`, `PARENT_CHUNK`.
  - Semantic graph dùng thêm node `Entity`, cạnh `MENTIONED_IN` từ entity sang chunk và cạnh `SEMANTIC_RELATION` giữa entity với thuộc tính `relation_type`. Không tạo cứng một bảng Kuzu cho từng relation type, để ontology vận hành phần mềm có thể mở rộng mà không đổi schema.
  - `app/graphrag/graph_database/ontology.py` định nghĩa allowlist entity/relation cho tài liệu quản trị phần mềm. `semantic_extraction.py` gọi LLM qua `GraphRAGAIClient`, parse JSON, loại entity/relation ngoài allowlist rồi mới persist.
  - `POST /api/v1/ingest` luôn lưu graph structure vào Kuzu sau khi chunk tài liệu. Structure graph `Document -> Element -> Chunk` đến từ parser/chunker và không cần LLM. Route mặc định `extract_semantic_graph=true`, hydrate LLM gateway từ PostgreSQL và trích xuất thêm knowledge graph `Entity -> relation -> Entity`; `llm_profile_id` là filter profile tùy chọn.
  - Kuzu store có traversal theo tên entity và traversal từ vector-selected chunk -> entity -> semantic neighbors -> related chunks. Retrieval orchestrator và `POST /api/v1/ingest/query` dùng traversal chunk-based để mở rộng context nếu semantic data tồn tại.
  - Startup FastAPI gọi `get_kuzu_graph_store().ensure_schema()`.
  - `app/graphrag/ingestion_pipeline.py`, `query_pipeline.py`, `engine.py` đã có wrapper tối thiểu nối sang graph/retrieval thay vì để rỗng.
- Visualize:
  - Đã tạo route `app/api/v1/visualize.py` với namespace `/api/v1/visualize`.
  - Đã tạo service `app/services/visualize/`.
  - Endpoint `POST /api/v1/visualize/vector/search` phục vụ search debugger: nhận query, embed query, search LanceDB, trả rank/top matches, similarity, distance, chunk text, metadata và graph context nếu có.
  - Endpoint `POST /api/v1/visualize/vector/health` trả embedding profile health theo document/profile/dimension/chunk count/missing embedding.
  - Endpoint `POST /api/v1/visualize/graph` trả payload ổn định cho Cytoscape: `nodes`, `edges`, `stats`, có filter scope/document và cờ bật/tắt structure/semantic graph.
  - `document_id` trong request vector health chỉ là filter tùy chọn. Nếu frontend không gửi `document_id`, service phải tự liệt kê record theo tenant/app/collection trong LanceDB và Kuzu rồi group theo các `document_id` đang có.
  - Vector health trả `embedding_dimension` lấy từ `embedding_model_profiles.embedding_dimensions` trong PostgreSQL và `vector_dimension` suy ra từ vector thực tế trong LanceDB. Vector ghi mới phải lưu UUID masterdata trong `embedding_profile_id`. Với vector cũ đã lưu `embedding_profile_id="runtime-embedding-pool"`, service fallback đối chiếu `embedding_model` đã index với model profile PostgreSQL; nếu nhiều profile cùng model nhưng khai báo dimension mâu thuẫn thì giữ `dimension_status="unknown"` thay vì đoán.
  - Frontend `/admin/documents` có khung `Visualization` với 2 tab `Vector` và `Graph`.
  - `ui/src/pages/documents_visualize/VectorVisualizationPage.vue` đã có UI thực tế cho Vector: một ô nhập test query, kết quả top matches và bảng embedding health. Hiện mặc định gửi scope dev `tenant-a`/`app-a`, `top_k=5`, `min_similarity=0.4`.
  - `ui/src/pages/documents_visualize/GraphVisualizationPage.vue` đã gọi graph visualize API và hiển thị graph bằng Cytoscape.js. Structure node label dùng title/excerpt/page/chunk index thay vì chỉ hiện `paragraph`, `heading` hoặc số chunk.
- Chat GraphRAG MVP:
  - Endpoint `POST /api/v1/chat/completions` dùng workflow embedding-first. Nhóm hard-block từ chối ngay không gọi model; request còn lại luôn embed query và search LanceDB trước. Chỉ vector matches đạt threshold mới được đưa vào context graph/RAG, sau đó gọi đúng một LLM để chọn `grounded_answer|social|refuse` và tạo phản hồi.
  - Endpoint `POST /api/v1/chat/completions/stream` giữ nguyên workflow completion và trả answer đã validate bằng SSE: một event `metadata`, các event `delta` theo từng ký tự và event `done`. Endpoint JSON `/completions` vẫn được giữ để tương thích client cũ.
  - `app/services/chat/behavior.py` hiện tập trung placeholder identity/personality/style, phạm vi smalltalk, nhóm nội dung hard-block, refusal variants ngẫu nhiên và runtime knobs. Sau này cần hydrate theo tenant/app/widget config thay vì để mặc định platform.
  - `app/services/chat/policy.py` dựng và parse JSON contract duy nhất `grounded_answer|social|refuse`, kiểm tra lại social answer và chỉ nhận grounded answer có citation hợp lệ. Khi không có context đạt threshold, backend cấm grounded answer dù LLM cố trả lời.
  - Chat completion không nhận `top_k` hoặc `min_similarity` từ frontend. Similarity threshold mặc định hiện tại `0.5` và fallback retrieval top-k `5` nằm trong behavior; retrieval top-k ưu tiên `embedding_model_profiles.retrieval_top_k` của profile mới nhất nếu có. `llm_model_profiles.top_k` chỉ là sampling parameter của provider và bị bỏ qua khi null hoặc `0`.
  - Context budget cấu hình qua các biến `CHAT_CONTEXT_*`.
  - Response chat trả `response_type`, answer, retrieval strategy và citation tối thiểu; không đẩy raw vector metadata/debug payload sang UI chat hoặc vào prompt LLM.
  - `ui/src/views/EmbedChatView.vue` là màn hình chat full-page thực tế, gọi completion SSE bằng `fetch()` + `ReadableStream`, ghép các character delta, giữ history ngắn theo session, hiển thị loại phản hồi và citation mở rộng khi cần.
- Tests:
  - Đã thêm test cho Kuzu structure/semantic graph, label visualization, traversal, visualization payload, parser ontology allowlist, runtime embedding/LLM gateway, chat completion context budget, SSE event stream, vector visualization service và AI Gateway error behavior.
  - Lệnh backend kiểm tra đang pass ở thời điểm 01/06/2026:
    - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s test`
    - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q app`
  - Sau thay đổi SSE ngày 01/06/2026 chưa chạy lại `cd ui && npm run build` theo yêu cầu của người dùng; cần chạy khi kiểm tra frontend chính thức.
  - Sau refactor lifecycle document, dữ liệu test cũ trong `data/lancedb` và `data/kuzu` đã được clean. Kuzu chỉ còn schema rỗng để backend khởi động; LanceDB chưa còn table vector.

### Chưa Hoàn Thành

- Chưa dùng LlamaIndex ChatEngine và Workflows. Đây là chủ đích giai đoạn 1: hiện chỉ dùng QueryEngine retrieval-only; giai đoạn sau thêm memory và workflow routing text/multimodal/deep-graph/parallel path.
- Chat MVP đã có hybrid retrieval, prompt synthesis, citation, gọi LLM gateway và SSE streaming answer đã validate; chưa có auth, persistence chat session/history và reranking production.
- `POST /api/v1/ingest/query` và visualize vector vẫn là retrieval/debug riêng; answer synthesis nằm ở `POST /api/v1/chat/completions`.
- Scope hiện tại cho frontend visualize còn hard-code dev `tenant-a`/`app-a`; cần thay bằng tenant/app context thật khi bước đa tenant được triển khai.
- Chưa có community detection Leiden/Louvain và community summary.
- Chưa có job queue/background worker cho ingestion; route ingest hiện xử lý trực tiếp trong request.
- Chưa có auth/permission boundary production cho Platform Admin, Customer Admin, End User.
- Chưa có dashboard usage/alert hoàn chỉnh cho AI Gateway dù usage event đã có model/table.
- Chưa có hardening CORS/embed origin/postMessage production.

### Việc Nên Làm Tiếp Theo

1. Sửa dứt điểm cấu hình provider/model profile trên `/platform` bằng dữ liệu thật:
   - Tạo provider.
   - Tạo API key.
   - Tạo embedding model profile.
   - Tạo LLM model profile.
   - Test embedding/LLM trước khi ingest.
2. Dùng `/admin/documents` ingest tài liệu thật, kiểm tra Vector tab:
   - Search debugger có trả đúng chunk không.
   - Similarity có hợp lý không.
   - Embedding health không mismatch dimension.
3. Kiểm tra Graph tab sau khi upload lại dữ liệu sạch:
   - So sánh số node/edge với số chunk/element của đúng một tài liệu.
   - Kiểm tra filter document và các quan hệ next/parent/source cùng semantic relations.
4. Test luồng chat GraphRAG bằng dữ liệu thật:
   - Upload lại tài liệu để tạo semantic graph bằng LLM.
   - Gọi `/embed/chat` và kiểm tra SSE character streaming, câu trả lời cùng citation.
   - Theo dõi token usage, điều chỉnh chunk size/context budget và bổ sung rerank nếu retrieval còn dư context.
5. Thêm nền job async:
   - Upload nhanh.
   - Worker ingest/index.
   - Retry/idempotency.
   - Progress status cho UI.
6. Khi ổn luồng đơn giản, mới mở rộng tenant/app/auth/quota production.
