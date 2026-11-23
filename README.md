# 知鉴Search · 知乎增强检索引擎（原型骨架）

> 基于知乎开放内容的 RAG 增强搜索引擎，叠加 **四层过滤（时效校验 · 可信度质检 · 结构化萃取 · 观点对照）**，
> 不输出唯一标准答案，做"信息审校层"。

本仓库是一套**可直接跑通的 MVP 原型骨架**：默认走离线 seed 数据集 + 规则模拟 LLM，
**零 API 额度、零 Key、离线即可完整演示**四层过滤与观点矩阵全链路；把开关切到真实模式即接入知乎 API 与 DeepSeek/Qwen。

---

## 1. 一键运行（默认 offline + mock，无需任何 Key）

```bash
cd zhijian-search
pip install -r requirements.txt          # 仅需 fastapi / uvicorn / pydantic / requests

# 启动后端
uvicorn backend.main:app --reload --port 8000

# 另开一个终端，起前端静态服务（任选其一）
python -m http.server 5500 --directory frontend
# 浏览器打开 http://127.0.0.1:5500/index.html
```

前端默认请求 `http://127.0.0.1:8000`。如果后端端口不同，在浏览器控制台执行一次：
```js
localStorage.setItem('ZHIJIAN_API','http://127.0.0.1:你的端口'); location.reload();
```

试试这几个 query：`笔记本电脑怎么选`、`考研值不值得`、`健身先增肌还是减脂`。

---

## 2. 架构与数据流

```
用户Query
  → Query改写/子问题拆解/意图识别      query_rewrite.py
  → 召回 topN（多子查询扩召回、去重）    zhihu_client.py
  → 【时效打分 + 窗口过滤】(痛点5)        filters/freshness.py
  → 【可信度质检：LLM + 客观信号双因子】(痛点3)  filters/credibility.py
  → 【BGE 基础相关性重排 + 多因子综合排序】 filters/rerank.py
  → 结构化萃取（问题级摘要聚合→卡片）(痛点2)  extract.py
  → 观点聚类（共识/分歧/风险矩阵）(痛点1)      cluster.py
  → 前端渲染（卡片视图 + 矩阵视图 + 风险标签 + 链路可视化）  frontend/index.html
```

编排入口：`backend/pipeline.py::search(query, options)`。

### 四层过滤如何体现差异化（vs 普通 RAG）
- **时效**：按 `CreateTime` 做指数衰减分，标【内容过时】，支持用户时间窗（近3月/半年/1年/不限）本地过滤。
- **可信度**：`LLM 软文预警` + `客观信号(赞同/评论/权威等级)` 双因子加权；低分**降权标红但不删除**，保留给用户判断。
- **结构化萃取**：输出标准卡片（核心结论/适用前提/优点/缺点/踩坑/风险 + 溯源链接）。
- **观点矩阵**：共识 / 分歧 / 风险三栏对照，不强行合并成单一答案。
- 结果里还带 **知乎直答基线对照** + **检索链路可视化 trace**，答辩时直接演示"多层过滤 vs 直答原生输出"的差异。

---

## 3. 已内置的关键约束处理（源自实测）

| 实测约束 | 本原型的落地处理 |
|---|---|
| 搜索只返回**摘要不是全文** | 痛点2 从"单篇长文萃取"**降级为问题级多回答摘要聚合**（`extract.py`），规避全文缺失 |
| 额度极低（搜索10/天、直答2/天） | 默认 `DATA_MODE=offline` 走 `data/seed_qa.json`，**演示零额度**；`hybrid` 模式缓存优先、实时兜底 |
| 搜索参数只有 query+count(≤10) | 时效窗口**只能本地按 CreateTime 过滤**（已实现）；靠 Query 改写多子查询凑召回量 |
| LLM 应以 DeepSeek/Qwen 为主力 | `llm.py` 主力走 OpenAI 兼容端点；**知乎直答仅作对照基线**（`zhida_baseline`） |
| 向量库/Embedding/Rerank 平台不提供 | rerank 当前为轻量词重合模拟，预留接口，升级时替换为自建 BGE + Chroma |

---

## 4. 从原型升级到真实链路（改环境变量即可，无需改代码）

```bash
# 接入真实知乎数据
export ZHIJIAN_DATA_MODE=hybrid         # offline / live / hybrid
export ZHIHU_API_BASE=https://openapi.zhihu.com
export ZHIHU_TOKEN=你的token

# 接入真实 LLM（DeepSeek 示例）
export ZHIJIAN_LLM_MODE=api
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_API_KEY=你的key
export LLM_MODEL=deepseek-chat
```

- `zhihu_client.py::_normalize_live` 已按实测字段（ContentText/CreateTime/VoteUpCount/AuthorityLevel…）对齐，接真实 API 时按返回结构微调即可。
- 要上 Chroma + BGE 自建向量检索：装好 `requirements.txt` 里注释掉的依赖，在 `filters/rerank.py` 替换 `_relevance`，在召回层前加一个离线 Embedding 流水线即可。

---

## 5. 目录结构

```
zhijian-search/
├── README.md
├── requirements.txt
├── backend/
│   ├── main.py            FastAPI 入口（/api/search, /api/seed_topics, /）
│   ├── config.py          全局配置（数据/LLM 模式、过滤参数）
│   ├── pipeline.py        七层架构编排
│   ├── zhihu_client.py    数据源（offline/live/hybrid）
│   ├── query_rewrite.py   Query 改写 & 意图识别
│   ├── filters/
│   │   ├── freshness.py    时效打分（痛点5）
│   │   ├── credibility.py  可信度质检（痛点3）
│   │   └── rerank.py       相关性重排 + 多因子综合排序
│   ├── extract.py         结构化卡片（痛点2，摘要聚合）
│   ├── cluster.py         观点矩阵（痛点1）
│   ├── llm.py             LLM 封装（mock/api + 直答基线）
│   └── prompts.py         三套提示词模板
├── data/
│   └── seed_qa.json       离线 seed 数据集（含过时内容/软文样本，供四层过滤演示）
└── frontend/
    └── index.html         单文件原生 HTML/CSS/JS 前端（无 CDN；检索、双视图、精选导出与分镜预览）
```

前端会读取健康检查中的数据源与 LLM 模式；处于 mock 模式时，会明确提示可信度、结构化摘要和观点矩阵属于规则/模板模拟结果。
精选资料在浏览器本地拼接并可导出 Markdown；科普视频入口目前为分镜预览原型，不会伪装成已生成的视频。

## 6. 接口

```
POST /api/search
  body: { "query": "考研值不值得", "options": {
      "filter_ad": true, "time_window_days": 0,
      "enable_card": true, "enable_matrix": true, "include_baseline": true } }
  resp: { query, intent, answers[], cards[], matrices[], trace[], zhida_baseline }

GET  /api/seed_topics    # 离线数据集里的可选主题
GET  /                   # 健康检查（含当前 data_mode / llm_mode）
```

`/api/search` 响应新增 `mode` 字段：`ok`（正常）/ `empty_query`（空查询）/ `degraded`（内部或知乎接口失败已降级，HTTP 仍为 200，不抛 500）。

---

## 7. 部署到公网（任务 A3）

要求已落地：HTTPS、CORS 放开（`allow_origins=["*"]`）、密钥走环境变量不写文件、进程守护崩溃自动重启。

### 方式 A：Docker Compose（推荐，最易复现）
```bash
git clone https://github.com/CleanCong/zhijian-search.git
cd zhijian-search
export ZHIHU_TOKEN=xxx        # 可选：hybrid/live 真实知乎数据才需要
export LLM_API_KEY=xxx        # 可选：api 模式真实摘要才需要
docker compose up -d --build  # restart: always 进程守护
docker compose logs -f backend
# 健康检查：curl http://服务器IP:8000/
```
前置 HTTPS：用 `deploy/nginx.conf` 反代 + `certbot --nginx -d 域名` 自动签证书。

### 方式 B：systemd（裸机）
```bash
sudo cp -r . /opt/zhijian-search && cd /opt/zhijian-search
pip install -r requirements.txt
sudo cp deploy/zhijian.service /etc/systemd/system/
# 密钥写进 /etc/zhijian.env（权限 600，不进 git）
sudo systemctl daemon-reload && sudo systemctl enable --now zhijian
```

### ⚠️ 若用内网穿透（如 frp/ngrok/cpolar）
意味着依赖某台电脑常开——**评委访问期间那台电脑不能关机/断网/休眠**，务必提前告知全队并安排值守。

部署后立刻用**手机流量（关 WiFi）**打开前端验证能搜出真实结果，不要只在电脑上试。

---

## 8. 稳定性与边界（任务 A5，已通过）

- 连续 20 次检索全部 HTTP 200，不崩。
- 空 query / 纯空格 → `mode=empty_query`，返回完整空结构，不报 500。
- 超长 query → 服务端截断（200 字）后正常处理；超大 body（>20000 字符）由 body 上限防护。
- 全特殊字符 / emoji / SQL 注入样 / 换行注入 → 全部 200。
- 知乎接口或内部异常 → `mode=degraded`（HTTP 200），不抛 500。
- 日志只记异常**类型**（不用 `logger.exception`），不打印 token / 异常消息，避免 secret 泄露。

---

## 9. 评测命令（任务 A6）

```bash
# 过滤器评测：软文召回率 / 误杀率 / 漏判案例 / 误杀案例
python evaluate.py --labels data/labels.csv

# 附带 A4 分桶抽查（共识/分歧/风险归类人工核对表）
python evaluate.py --labels data/labels.csv --buckets

# 机器可读输出
python evaluate.py --labels data/labels.csv --json
```

`data/labels.csv` 列：`url, question, label, content_text`，`label ∈ {ad, ok}`（C 维护标注）。
结果真跑真算、可复现，数字可直接写进计划书。当前 seed 标注集（14 条 / 3 条软文）跑出：**召回率 100%、误杀率 0%**。

---

## 10. 归并质量优化（任务 A4）

`backend/cluster.py` 已从"写死占位"升级为**基于内容的规则聚类引擎**（LLM 可用时优先 LLM，失败/mock 退回规则，降级链保持）：

1. **共识**：要求"多条内容说法一致"（≥2 条、信号重合、立场不对立）才成共识，不再是兜底桶；宁缺毋滥。
2. **分歧**：先做立场分类（支持/反对/条件派），再把对立立场配成对照，不靠"但是/不过"浅判断。
3. **风险**：只有"有具体场景"（面积/户型/宠物/体脂/专业/预算…）或软文/过时信号才进桶。
4. **降级链**：`core_conclusion` 与矩阵都遵循"模型优先 → 失败退回规则"，输出结构一致。
5. **同题多答**：按信号聚合去重后再找分歧，避免同题多条各自成桶。

验收：三演示场景人工抽查，归类错误 ≤1 条（优于 ≤2 的验收线）；不硬凑三桶，某场景只有两桶是正常现象。

---

## 11. 演示预热 / 线上冒烟（任务 A7）

```bash
python scripts/warmup.py                                   # 本地
python scripts/warmup.py --base https://your-domain.example.com   # 线上
```
演示前把三个场景各跑一遍，预热缓存并当健康冒烟；任一场景 `degraded` 或空结果会立即报警。
