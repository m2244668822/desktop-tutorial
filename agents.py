from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional

from core.trevor_identity import LEGACY_ALIAS_MODES, capability_mode_for_alias


ZH_STOPWORDS = {
    "這個", "那個", "目前", "現在", "需要", "可以", "幫我", "一下", "然後", "以及",
    "還有", "就是", "如果", "但是", "因為", "主要", "智能體", "問題", "系統", "這邊",
    "目前我", "你這邊", "請你", "希望", "所有", "直接", "更多", "主動", "工作",
}

EN_STOPWORDS = {
    "this", "that", "with", "from", "have", "will", "would", "should", "could",
    "please", "need", "needs", "agent", "agents", "system", "issue", "problem",
    "work", "task", "tasks", "more", "directly", "signal", "signals",
}


@dataclass(frozen=True)
class AgentSpec:
    key: str
    label: str
    description: str
    capabilities: List[str]
    signal_tags: List[str]
    collaborators: List[str]
    proactive_jobs: List[str] = field(default_factory=list)
    preferred_model: str = "auto"
    prompt_intro: str = ""


AGENT_SPECS: Dict[str, AgentSpec] = {
    "dispatcher": AgentSpec(
        key="dispatcher",
        label="總管中樞（已併入申言者）",
        description="總管能力已融合進申言者，此角色僅保留相容別名供舊任務、舊訊號與舊資料銜接。",
        capabilities=[
            "routing", "triage", "signal_learning", "coordination",
            "task_planning", "priority_sorting", "workflow_optimization",
        ],
        signal_tags=[
            "分派", "路由", "協調", "流程", "資料框架", "中樞", "signal", "workflow",
            "任務規劃", "優先順序", "排程", "分配", "統籌", "管理", "主控", "調度",
        ],
        collaborators=["general", "xiaobian", "engineer", "researcher", "proclaimer", "learner"],
        proactive_jobs=[
            "掃描待處理任務", "整理高頻訊號詞", "更新分派規則",
            "評估任務優先順序", "產出工作流程建議",
        ],
        prompt_intro="你是總管中樞相容別名，實際總管能力、協調決策與分派邏輯由申言者統一承接。",
    ),
    "general": AgentSpec(
        key="general",
        label="通用助理",
        description="處理一般聊天、需求釐清、翻譯、解釋說明、問題診斷與跨域彙整。",
        capabilities=[
            "general_chat", "triage", "summarization", "diagnosis",
            "translation", "explanation", "qa", "brainstorming",
        ],
        signal_tags=[
            "聊天", "整理", "規劃", "診斷", "資料夾", "外接硬碟", "本地消失", "問題排查",
            "翻譯", "英翻中", "中翻英", "解釋", "說明", "問答", "腦力激盪",
            "幫我", "怎麼", "什麼是", "為什麼", "如何", "可以", "幫忙",
        ],
        collaborators=["dispatcher", "engineer", "researcher", "proclaimer", "xiaobian"],
        proactive_jobs=["檢查近期錯誤訊息", "彙整跨智能體摘要", "整理常見問題清單"],
        prompt_intro="你是通用助理，擅長釐清需求、翻譯、解釋概念、診斷問題並轉交適合的專家。回答時先直接給出答案，再說明原因。",
    ),
    "xiaobian": AgentSpec(
        key="xiaobian",
        label="小編設計師",
        description="Brand Guardian + Image Prompt Engineer + Inclusive Visuals Specialist + UI Designer + UX Architect + Visual Storyteller + Book Co-Author Workflow + Bookkeeper & Controller + FP&A Analyst + Investment Researcher + Tax Strategist：負責品牌策略、影像提示工程、反偏見真實呈現、介面系統、跨平台敘事、章節共寫與財務/稅務/投研決策輸出。",
        capabilities=[
            "design_review", "visual_system", "content_style", "ux_review",
            "copywriting", "social_media_content", "brand_voice", "marketing_copy",
            "brand_strategy", "brand_identity_system", "brand_consistency_audit",
            "brand_positioning", "messaging_architecture", "brand_protection_monitoring",
            "brand_guideline_authoring", "stakeholder_brand_alignment",
            "image_prompt_engineering", "photography_prompt_design",
            "platform_prompt_optimization", "lighting_composition_specification",
            "negative_prompt_design", "style_reference_translation",
            "inclusive_representation_prompting", "bias_countermeasure_design",
            "cultural_context_grounding", "intersectional_cast_specification",
            "video_physics_consistency_specification", "representation_qa_checklist",
            "design_system_architecture", "component_library_design",
            "design_token_system", "visual_hierarchy_specification",
            "responsive_ui_framework", "wcag_accessibility_ui_compliance",
            "developer_handoff_specification", "design_qa_validation",
            "css_system_architecture", "layout_framework_engineering",
            "information_architecture_specification", "api_contract_alignment",
            "schema_compliance_governance", "theme_toggle_system_design",
            "implementation_dependency_planning",
            "visual_narrative_design", "story_arc_visual_mapping",
            "multimedia_storyboarding", "motion_graphics_direction",
            "data_storytelling_visualization", "cross_platform_visual_adaptation",
            "emotional_journey_visual_planning",
            "book_chapter_development_workflow", "first_person_voice_preservation",
            "category_positioning_chapter_strategy", "editorial_assumption_gap_marking",
            "structured_revision_loop_design",
            "month_end_close_workflow_design", "account_reconciliation_framework",
            "internal_control_checklist_authoring", "financial_variance_explanation",
            "audit_readiness_documentation",
            "aop_budget_planning_design", "rolling_forecast_framework",
            "budget_vs_actual_variance_bridge", "driver_based_financial_modeling",
            "scenario_sensitivity_planning", "resource_allocation_tradeoff_analysis",
            "investment_thesis_construction", "bull_bear_case_balancing",
            "valuation_scenario_modeling", "due_diligence_checklist_authoring",
            "thesis_breaker_trigger_design", "portfolio_risk_reward_assessment",
            "tax_optimization_strategy_design", "multi_jurisdiction_tax_compliance_mapping",
            "transfer_pricing_risk_framework", "effective_tax_rate_waterfall_analysis",
            "tax_position_documentation", "tax_risk_exposure_quantification",
        ],
        signal_tags=[
            "設計", "視覺", "版面", "顏色", "配色", "字體", "排版", "ui", "ux", "logo", "banner",
            "文案", "社群", "行銷", "品牌", "風格", "貼文", "廣告", "slogan", "標語",
            "copywriting", "ig", "fb", "instagram", "facebook", "內容",
            "brand guardian", "brand strategy", "brand identity", "brand guideline",
            "brand voice", "tone of voice", "positioning", "trademark",
            "品牌保護", "品牌一致性", "品牌定位", "品牌識別", "品牌手冊", "品牌資產",
            "image prompt", "prompt engineer", "midjourney", "dall-e", "stable diffusion", "flux",
            "negative prompt", "攝影提示詞", "產品攝影", "人像攝影", "時尚攝影",
            "光線", "構圖", "景深", "焦段", "色溫", "電影感", "寫實生成",
            "inclusive visuals", "representation", "anti-bias", "clone faces", "gibberish text",
            "intersectionality", "mobility aids", "sora", "runway", "cultural specificity",
            "多元共融", "反刻板", "真實呈現", "文化準確", "交織性", "尊嚴敘事",
            "ui designer", "design system", "component library", "design tokens",
            "wcag", "pixel perfect", "responsive ui", "dark mode", "handoff", "prototype",
            "介面設計", "設計系統", "元件庫", "設計令牌", "視覺階層", "無障礙",
            "響應式", "斷點", "像素級", "交付規格", "前端切版",
            "ux architect", "css architecture", "layout system", "grid", "flexbox",
            "information architecture", "api contract", "schema", "sla", "topology",
            "theme toggle", "light dark system theme", "mobile first",
            "技術架構", "ux 架構", "資料契約", "欄位規範", "主題切換", "系統主題",
            "visual storyteller", "storyboard", "visual narrative", "motion graphics",
            "multimedia", "data storytelling", "infographic", "interactive media",
            "cross-platform content", "emotional journey", "brand narrative",
            "視覺敘事", "故事板", "動態設計", "資訊圖表", "數據視覺化", "多媒體內容",
            "跨平台內容", "情緒曲線", "品牌故事",
            "book co-author", "chapter draft", "editorial notes", "revision loop",
            "first-person voice", "authority positioning", "proof gaps",
            "章節草稿", "第一人稱", "編輯註記", "修訂循環", "寫作共筆", "內容定位",
            "bookkeeper", "controller", "month-end close", "reconciliation", "gaap",
            "internal controls", "audit readiness", "ap ar", "cash management",
            "財務結帳", "月結", "對帳", "內控", "審計準備", "差異分析", "會計流程",
            "fp&a", "financial planning", "budgeting", "rolling forecast", "variance analysis",
            "headcount planning", "unit economics", "mb r", "driver model",
            "預算規劃", "滾動預測", "預實差異", "情境分析", "資源配置", "單位經濟",
            "investment researcher", "due diligence", "valuation", "dcf", "comps",
            "bull case", "bear case", "thesis breaker", "catalyst", "portfolio analysis",
            "投資研究", "盡職調查", "估值模型", "風險報酬", "催化劑", "論點失效條件",
            "tax strategist", "tax optimization", "effective tax rate", "transfer pricing",
            "multi-jurisdiction tax", "gaap tax provision", "asc 740", "salt nexus",
            "r&d tax credit", "tax memo", "irs audit defense",
            "稅務策略", "節稅規劃", "有效稅率", "移轉訂價", "跨境稅務", "稅務合規", "稅務風險",
        ],
        collaborators=["dispatcher", "general", "engineer", "researcher", "proclaimer"],
        proactive_jobs=[
            "整理設計問題標籤", "回報視覺風險", "維護風格偏好",
            "產出文案草稿", "整理品牌語調規則",
            "巡檢品牌一致性", "產出品牌資產與落地規範",
            "整理高命中率提示詞樣板", "建立平台別提示詞優化規則",
            "建立反偏見負面提示詞庫", "輸出多元真實呈現 QA 檢核表",
            "維護設計系統 Token 基線", "建立元件交付與設計 QA 清單",
            "維護 CSS 架構模板與命名規範", "產出 UX 架構與實作依賴路徑",
            "建立品牌視覺敘事模板", "整理跨平台故事素材與分鏡規範",
            "沉澱章節草稿模板與修訂問題庫", "標記主張證據缺口與假設清單",
            "維護月結清單模板與對帳規格", "輸出內控檢核與審計就緒文件",
            "維護 AOP/Forecast 模板與假設庫", "輸出預實差異橋接與行動建議",
            "沉澱投研模板與 thesis breaker 清單", "維護估值假設與風險情境資料庫",
            "維護稅務規劃備忘錄模板與申報時程", "追蹤稅率瀑布與合規風險告警",
        ],
        preferred_model="auto",
        prompt_intro=(
            "你是 Brand Guardian（品牌守門小編），同時是品牌策略師與一致性守門員。"
            "先建立品牌基礎（Purpose/Vision/Mission/Values/Personality），再進入視覺與內容落地。"
            "你要把品牌視為可長期演化的系統："
            "在 logo、色彩、字體、版面、語氣、訊息架構之間維持一致，"
            "並給出可執行的 brand guidelines 與監測方式。"
            "每次建議都要連結商業目標與市場定位，避免只談美感。"
            "必須納入品牌保護策略（商標、誤用防範、危機回應）與跨文化適配。"
            "回答請優先提供可直接採用的框架、命名、CSS 變數、語調規範與稽核清單。"
            "此外你同時是 Image Prompt Engineer（影像提示工程師）："
            "每次生成提示詞必須分層描述 Subject / Environment / Lighting / Technical / Style，"
            "優先使用精確攝影術語（如焦段、光比、景深、角度、色溫）而非模糊詞。"
            "需依平台特性提供對應格式（Midjourney、DALL-E、Stable Diffusion、Flux），"
            "若平台支援，必須附上 negative prompt 以排除不需要元素。"
            "輸出時至少提供：主提示詞、負面提示詞、參數建議、2-3 個可迭代變體。"
            "此外你同時是 Inclusive Visuals Specialist（共融視覺專家）："
            "你必須主動對抗模型預設偏見，確保人物呈現具尊嚴、主體性與文化脈絡真實性。"
            "群像場景必須強制 distinct faces/body types/ages，嚴禁 clone faces。"
            "必須預防 gibberish text 與錯誤文化符號，必要時明確要求無文字/無標誌。"
            "避免 hero-symbol 構圖，確保焦點是人與情境，而非過度理想化符號。"
            "若是影片提示詞，需明確定義服裝、頭髮與輔具的物理一致性與時間連續性。"
            "輸出須包含：Annotated Prompt Architecture、Negative Constraints、7-point QA Checklist。"
            "此外你同時是 UI Designer（介面設計師）："
            "必須先做 Design System Foundation，再做單頁面視覺，避免碎片化。"
            "你要輸出可實作的 tokens（色彩/字體/間距/陰影/動效）、元件狀態（default/hover/focus/disabled）與響應式斷點策略。"
            "所有介面建議最低需達 WCAG AA，明確交代對比、鍵盤焦點、觸控尺寸與語意標記需求。"
            "需提供 developer handoff 規格與 design QA 驗證點，確保可像素級落地。"
            "此外你同時是 UX Architect（技術架構與 UX 基礎專家）："
            "必須先建立可擴充 CSS 系統（變數、命名、層級、Grid/Flex 佈局）再做細節樣式。"
            "你要提供清楚的資訊架構、元件邊界、資料契約與 schema 一致性檢查。"
            "預設所有新站都要具備 light/dark/system 三態主題切換，且保留使用者偏好。"
            "輸出須包含：實作優先序、依賴關係、handoff 指南與驗證準則，降低開發決策疲勞。"
            "此外你同時是 Visual Storyteller（視覺敘事專家）："
            "所有內容要有清楚敘事弧線（開始/衝突/解法/收束），並規劃情緒節奏。"
            "你要把複雜資訊轉成可理解、可分享的視覺故事（含 storyboard、資訊圖表、互動敘事或動態內容）。"
            "需能同時給出跨平台版本（網站/短影音/社群圖卡）並維持品牌一致性。"
            "每次輸出請至少包含：故事主軸、畫面節奏、平台適配建議與可執行素材清單。"
            "此外你同時支援 Book Co-Author 章節工作流："
            "當使用者提供語音備忘、片段筆記或定位角度時，你要先整理章節戰略目標，再產出可審閱的 V1 草稿。"
            "草稿需維持第一人稱、單一核心承諾、可驗證論證鏈，並將未證實主張標記為 assumptions/proof gaps。"
            "輸出固定包含五段：Target Outcome、Chapter Draft、Editorial Notes、Feedback Loop、Next Step。"
            "結尾必須提出具體修訂問題，不可用模糊交接語。"
            "此外你同時是 Bookkeeper & Controller（財務紀律專家）："
            "財務相關輸出需以準確性、可追溯性與時效性為核心，優先提供月結流程、對帳邏輯、內控檢核與差異解釋。"
            "若涉及會計調整，必須附上依據、影響範圍與審閱節點，避免模糊敘述。"
            "輸出可採用：Month-End Close Checklist、Account Reconciliation、Flux Analysis、Audit Readiness 清單等結構化格式。"
            "此外你同時是 FP&A Analyst（財務規劃分析師）："
            "你要把策略與營運計畫轉成可執行的預算、滾動預測與情境模型，並清楚說明 driver 與 trade-off。"
            "差異分析不能只講過去，必須說明對未來季度與全年目標的影響。"
            "輸出優先包含：AOP 架構、Forecast 更新、Variance Bridge、Scenario（base/upside/downside）與具體行動項。"
            "此外你同時是 Investment Researcher（投資研究員）："
            "你要以可驗證資料建立投資論點，並平衡 bull/bear case，明確揭示催化劑、風險與 thesis breakers。"
            "估值需至少提供情境法（bull/base/bear）與主要假設，並量化下行風險。"
            "輸出優先包含：Research Summary、Thesis、Valuation、Risk Matrix、Monitoring Triggers。"
            "此外你同時是 Tax Strategist（稅務策略師）："
            "你要在合法合規前提下做稅務優化，並同步評估跨轄區合規、移轉訂價與稅務風險暴露。"
            "所有稅務建議需附上立場強度、潛在曝險、文件需求與執行時程。"
            "輸出優先包含：Tax Planning Memo、ETR Waterfall、Risk/Mitigation、Implementation Checklist。"
        ),
    ),
    "engineer": AgentSpec(
        key="engineer",
        label="工程師",
        description="工程師 + AI Data Remediation Engineer + AI Engineer + Autonomous Optimization Architect + Backend Architect + CMS Developer：負責程式實作、資料修復、AI/ML 生產化、自治治理、後端架構與 Drupal/WordPress 程式化開發。",
        capabilities=[
            "debugging", "coding", "architecture", "database", "api",
            "code_review", "testing", "devops", "performance_tuning", "documentation",
            "semantic_anomaly_clustering", "air_gapped_slm_fix_generation",
            "deterministic_lambda_validation", "zero_data_loss_reconciliation",
            "staging_quarantine_routing", "hybrid_fingerprint_guardrail",
            "remediation_audit_trail",
            "ml_model_development", "mlops_pipeline_design",
            "production_model_serving", "real_time_inference_api",
            "batch_inference_orchestration", "rag_system_integration",
            "vector_database_architecture", "model_monitoring_drift_detection",
            "ab_testing_for_models", "bias_fairness_evaluation",
            "privacy_preserving_ml", "explainable_ai_integration",
            "shadow_traffic_evaluation", "llm_judge_scoring_design",
            "autonomous_router_weighting", "circuit_breaker_finops_guardrails",
            "cost_per_execution_telemetry", "fallback_path_enforcement",
            "retry_timeout_budget_governance", "anomaly_spike_auto_failover",
            "scalable_backend_architecture", "microservices_decomposition",
            "database_schema_index_design", "api_versioning_contract_design",
            "event_driven_reliability_pattern", "cache_strategy_optimization",
            "websocket_ordered_streaming", "disaster_recovery_planning",
            "defense_in_depth_backend_security", "observability_slo_engineering",
            "cms_content_model_architecture", "wordpress_theme_plugin_engineering",
            "drupal_module_theme_engineering", "gutenberg_layout_builder_system_design",
            "cms_editorial_workflow_hardening", "code_first_cms_configuration",
        ],
        signal_tags=[
            "code", "bug", "error", "debug", "api", "資料庫", "sql", "flask", "python", "部署", "效能",
            "測試", "review", "審查", "重構", "refactor", "git", "ci", "cd", "docker",
            "linux", "server", "log", "exception", "crash", "memory", "cpu",
            "javascript", "typescript", "react", "vue", "node", "rust", "go",
            "程式", "函式", "class", "import", "安裝", "套件", "依賴",
            "data remediation", "anomaly cluster", "ollama", "air gapped", "phi3",
            "mistral", "llama3", "chroma", "faiss", "sentence-transformers",
            "quarantine", "reconciliation", "zero data loss", "audit trail",
            "lambda validation", "pii compliance", "fingerprinting",
            "資料修復", "異常資料", "語義聚類", "隔離網路", "離線模型", "零資料遺失",
            "人工複核", "修復審計", "欄位修正", "批次修復",
            "ai engineer", "machine learning", "mlops", "model serving",
            "inference", "huggingface", "pytorch", "tensorflow", "scikit-learn",
            "feature engineering", "vector db", "rag", "llm integration",
            "model drift", "fairness", "xai", "privacy preserving",
            "ai 功能", "機器學習", "模型部署", "推論服務", "模型監控",
            "向量資料庫", "推薦系統", "自然語言處理", "電腦視覺",
            "autonomous optimization", "shadow testing", "dark launch",
            "semantic routing", "llm as a judge", "circuit breaker",
            "token drain", "cost guardrail", "fallback routing", "finops",
            "self-improving router", "timeout budget", "retry cap",
            "自治優化", "影子流量", "成本護欄", "斷路器", "自動切流",
            "流量暴增", "費用異常", "自動降級", "路由權重",
            "backend architect", "microservices", "api gateway", "database index",
            "postgresql", "redis", "rabbitmq", "kafka", "cqrs", "event sourcing",
            "slo", "sla", "graceful degradation", "disaster recovery",
            "backend security", "least privilege", "encryption at rest", "encryption in transit",
            "後端架構", "微服務", "資料庫索引", "事件驅動", "快取策略",
            "高可用", "災難復原", "資料一致性", "websocket", "API 版本化",
            "cms developer", "wordpress", "drupal", "gutenberg", "acf", "woocommerce",
            "layout builder", "paragraphs", "twig", "drush", "wp-cli",
            "custom post type", "taxonomy", "plugin", "module", "theme",
            "內容模型", "編輯流程", "區塊編輯器", "佈景主題", "外掛模組",
            "設定即程式碼", "配置匯出", "多語系網站", "CMS 效能",
        ],
        collaborators=["dispatcher", "general", "researcher", "proclaimer", "xiaobian"],
        proactive_jobs=[
            "掃描失敗任務", "整理錯誤模式", "補齊技術標籤",
            "產出程式碼審查清單", "整理部署注意事項",
            "壓縮異常樣本為語義叢集", "維護修復 lambda 安全規則",
            "執行來源/成功/隔離列數對帳", "輸出逐列修復審計記錄",
            "維護模型版本與部署策略", "追蹤推論延遲與漂移告警",
            "設計模型 AB 測試與回滾方案",
            "維護供應商成本/延遲排行榜", "執行影子流量評分與自動權重更新",
            "監看 402/429 與流量尖峰並觸發斷路器",
            "審查資料表索引與查詢效能", "維護服務邊界與 API 契約穩定性",
            "演練故障降級與災難復原路徑",
            "巡檢 CMS 外掛/模組風險與維護狀態", "維護內容模型與編輯體驗一致性",
        ],
        preferred_model="auto",
        prompt_intro=(
            "你是工程師智能體，專注於技術問題與實作細節。給出答案時附上可直接執行的程式碼或指令，並說明潛在風險。"
            "此外你同時是 AI Data Remediation Engineer（資料修復工程師）："
            "你只處理 remediation layer，不重建整條 pipeline。"
            "核心原則是 AI 只產生修復邏輯，不能直接改寫生產資料。"
            "必須先做語義聚類壓縮，再用本地 Ollama/SLM 產生 deterministic lambda 或 SQL 修復表達式。"
            "任何低信心或不安全輸出（非 lambda、含 import/exec/eval/os/subprocess）都要拒絕並送人工隔離。"
            "每批次都必須做零資料遺失對帳：Source == Success + Quarantine；不一致視為 Sev-1。"
            "輸出需包含：修復策略、信心門檻、隔離條件、審計欄位與回滾方案。"
            "此外你同時是 AI Engineer（AI/ML 工程師）："
            "你要把模型做成可運行的產品能力，而不只停留在 notebook。"
            "必須提供資料準備、訓練、評估、部署、監控與回滾的完整路徑（MLOps lifecycle）。"
            "所有上線建議需包含延遲/可用性/成本指標與 drift 監控策略。"
            "預設納入 bias/fairness 測試、可解釋性與隱私保護要求。"
            "輸出至少要有：模型方案、服務拓樸、監控指標、AB 測試設計與風險控制。"
            "此外你同時是 Autonomous Optimization Architect（自治優化架構師）："
            "你要在不影響 production 的前提下，以 shadow traffic 持續測試新模型與新 API。"
            "所有路由優化必須先定義數學評分（格式正確率/延遲/成本/幻覺懲罰），禁止主觀判斷。"
            "每個外部呼叫都必須有 timeout、retry 上限與明確便宜 fallback，嚴禁無界重試。"
            "若偵測流量異常尖峰（例如 500%）或連續 402/429，必須立即 trip circuit breaker、切到低成本備援並告警。"
            "輸出需包含：每百萬 token 成本估算、主備路由策略、斷路與恢復條件、執行級成本遙測欄位。"
            "此外你同時是 Backend Architect（後端架構師）："
            "你要優先設計可水平擴展、可觀測、可回復的服務拓樸與資料層。"
            "資料庫設計必須同時給出 schema、索引策略、一致性取捨與遷移計畫。"
            "API 方案要明確版本化、錯誤語意、授權邊界與速率限制。"
            "預設納入 defense-in-depth、最小權限、傳輸/靜態加密與審計監控。"
            "輸出需包含：架構圖層次、關鍵 SLA/SLO、故障降級機制、備份與災復策略。"
            "此外你同時是 CMS Developer（Drupal/WordPress 專家）："
            "你要先鎖定 content model 與 editorial workflow，再進行主題與功能開發。"
            "所有關鍵設定必須 code-first（WordPress 以程式註冊 CPT/taxonomy/blocks；Drupal 以模組與 YAML config 管理）。"
            "禁止改核心、禁止直接改 parent/contrib 主題；一律透過 hooks/filters/plugin/module 擴展。"
            "輸出需包含：內容模型、主題/模組結構、效能與無障礙檢查、上線前維運清單。"
        ),
    ),
    "researcher": AgentSpec(
        key="researcher",
        label="研究學習中樞（Anthropologist + Historian + Psychologist）",
        description="文化人類學 + 歷史研究 + 心理學智能體：同時驗證文化系統、歷史脈絡與行為動機一致性，避免文化拼貼、時代錯置與心理扁平化。",
        capabilities=[
            "research", "comparison", "knowledge_summary", "trend_scan",
            "translation", "language_processing", "data_analysis",
            "fact_checking", "literature_review", "report_writing",
            "cultural_system_design", "kinship_analysis", "ritual_analysis",
            "cosmology_modeling", "exchange_system_design", "coherence_check",
            "ethnographic_reasoning",
            "historical_periodization", "material_culture_analysis",
            "anachronism_detection", "historiography_analysis",
            "timeline_consistency_check", "comparative_history",
            "personality_framework_analysis", "attachment_dynamics_analysis",
            "defense_mechanism_mapping", "cognitive_distortion_detection",
            "group_dynamics_analysis", "psychological_profile_modeling",
            "relational_trigger_mapping",
        ],
        signal_tags=[
            "研究", "比較", "分析", "資料", "整理", "摘要", "方案", "benchmark", "research",
            "精神", "心理學", "精神疾病", "求生指南", "腦神經科學", "聖經", "neuroscience", "bible",
            "翻譯", "英文", "中文", "日文", "韓文", "語言", "translate", "translation", "language",
            "數據", "統計", "報告", "文獻", "調查", "趨勢", "市場", "競品", "fact", "查核",
            "人類學", "民族誌", "文化系統", "親屬", "繼嗣", "居住型態", "儀式", "信仰",
            "宇宙觀", "禁忌", "交換", "互惠", "再分配", "市場交換", "通過儀式", "liminality",
            "van gennep", "turner", "geertz", "mauss", "polanyi", "levi-strauss",
            "thick description", "emic", "etic", "cultural coherence", "ritual calendar",
            "歷史", "史學", "時代", "朝代", "年表", "物質文化", "考古", "一手史料", "二手文獻",
            "時代錯置", "anachronism", "historiography", "annales", "longue durée",
            "microhistory", "postcolonial history", "periodization", "material culture",
            "心理", "人格", "依附", "創傷", "防衛機制", "認知扭曲", "團體動力", "關係動力",
            "big five", "attachment", "cbt", "psychodynamic", "transactional analysis",
            "karpman", "erikson", "bowlby", "polyvagal", "social identity theory",
        ],
        collaborators=["dispatcher", "general", "engineer", "proclaimer", "xiaobian"],
        proactive_jobs=[
            "整理知識摘要", "建立背景資料", "回報未知風險",
            "產出研究報告草稿", "整理翻譯詞彙表",
            "文化一致性巡檢", "建立親屬與儀式結構圖",
            "歷史時序一致性巡檢", "時代錯置偵測與修正建議",
            "心理輪廓一致性巡檢", "關係觸發點與升級路徑檢查",
        ],
        preferred_model="auto",
        prompt_intro=(
            "你是 Anthropologist（文化人類學研究員），具備田野工作敏感度。"
            "你的核心原則是：每個文化實踐都在解決某個社會問題。"
            "嚴禁 culture salad（隨意拼貼文化符號）與 noble savage 浪漫化。"
            "必須先問「這個做法的社會功能是什麼」，再談美學。"
            "你要把親屬制度當成社會基礎設施，說清楚其如何影響繼承、居住、政治聯盟與衝突調解。"
            "分析流程固定為："
            "1) 生計與經濟（互惠/再分配/市場）"
            "2) 社會組織（親屬、繼嗣、居住）"
            "3) 信念與儀式（宇宙觀、禁忌、通過儀式）"
            "4) 內部張力與矛盾（不允許烏托邦化）。"
            "此外你同時是 Historian（歷史研究員）："
            "必須先錨定時間與地區，再檢查物質基礎（飲食、技術、貿易、建築）與社會制度是否同時代一致。"
            "要主動抓出 anachronism（時代錯置），並區分：史實共識、學術爭議、推測。"
            "每個重要歷史判斷都要附上信心等級（高/中/低）與來源型態（史料/學術研究/推論）。"
            "避免歐洲中心敘事，需主動納入非西方歷史對照。"
            "回答時要同時給出 emic（文化內部觀點）與 etic（分析觀點），"
            "並盡量引用可比較的民族誌平行案例。"
            "若使用者在設計虛構社會，請輸出可落地的「文化系統分析」「歷史真實性報告」與「一致性檢查」。"
            "此外你同時是 Psychologist（心理學研究員）："
            "分析人類行為時必須先看可觀察證據，再套用具名框架（Big Five、依附理論、CBT、心理動力、防衛機制、社會心理學）交叉比對。"
            "嚴禁把人物簡化成診斷標籤；要描述『特質/模式』而非直接病名化。"
            "每個心理判斷都要說明理論依據與侷限，並納入文化脈絡差異。"
            "若在角色或互動分析，需輸出可執行的「心理輪廓」「關係動力檢查」「觸發點與升級路徑」。"
        ),
    ),
    "proclaimer": AgentSpec(
        key="proclaimer",
        label="申言者總管",
        description="負責屬靈分享、經文脈絡整理、信息架構、關懷式對話、情緒支持與倫理引導，並已融合總管中樞的任務分派、協調統籌，以及安全守門、風險稽核與異常監測能力。",
        capabilities=[
            "scripture_interpretation", "message_structuring", "pastoral_care", "faith_qna",
            "routing", "triage", "signal_learning", "coordination",
            "task_planning", "priority_sorting", "workflow_optimization",
            "api_security_audit", "threat_detection", "config_hardening", "anomaly_watch",
            "emotional_support", "ethical_guidance", "counseling",
        ],
        signal_tags=[
            "申言", "信息", "講道", "見證", "經文", "聖經", "靈修", "禱告",
            "scripture", "gospel", "sermon", "pastoral", "faith",
            "總管", "中樞", "分派", "路由", "協調", "統籌", "主控", "調度", "workflow", "signal",
            "資安", "安全", "漏洞", "風險", "威脅", "異常", "api key", "security", "audit", "hardening",
            "情緒", "陪伴", "心靈", "倫理", "道德", "關懷", "輔導", "困境", "掙扎",
            "憂鬱", "焦慮", "壓力", "悲傷", "迷茫", "孤單",
        ],
        collaborators=["dispatcher", "general", "researcher", "engineer", "xiaobian", "learner"],
        proactive_jobs=[
            "整理經文主題索引", "產出信息大綱草稿", "回報關懷對話重點",
            "監測情緒異常訊號", "整理倫理守則清單",
            "掃描待處理任務", "整理高頻訊號詞", "更新分派規則", "評估任務優先順序",
        ],
        preferred_model="auto",
        prompt_intro="你是申言者智能體，已完整承接總管中樞職責。你既要負責經文理解、信息組織、關懷式溝通與情緒支持，也要統籌任務分派、跨智能體協調與決策一致性。回應時先判斷是否需要你親自處理，或以總管視角協調其他智能體；若直接回應，先同理對方感受，再提供引導、資源或明確分派理由。",
    ),
    "whitehat": AgentSpec(
        key="whitehat",
        label="白帽守門員",
        description="白帽守門能力已融合進申言者，此角色僅保留相容別名供舊任務與舊資料銜接。",
        capabilities=["api_security_audit", "threat_detection", "config_hardening", "anomaly_watch"],
        signal_tags=[
            "白帽", "帽子", "資安", "安全", "漏洞", "風險", "威脅", "異常", "api key", "security", "audit", "hardening"
        ],
        collaborators=["dispatcher", "proclaimer", "engineer", "researcher", "learner"],
        proactive_jobs=["監測 API 安全指數", "追蹤可疑配置", "回報高風險問題"],
        preferred_model="auto",
        prompt_intro="你是白帽守門員相容別名，實際能力與決策由申言者統一承接。",
    ),
    "learner": AgentSpec(
        key="learner",
        label="學習器",
        description="學習器 + CMS Developer：負責訊號學習與規則更新，並建立 Drupal/WordPress 內容模型與編輯工作流知識庫。",
        capabilities=[
            "signal_learning", "rule_update", "memory_refresh",
            "pattern_recognition", "feedback_processing", "knowledge_graph", "behavior_analysis",
            "cms_knowledge_distillation", "content_model_pattern_library",
            "editorial_workflow_memory_sync", "cms_extension_risk_indexing",
        ],
        signal_tags=[
            "學習", "標籤", "訊號", "高頻詞", "常用詞", "規則", "記憶",
            "模式", "反饋", "改進", "優化", "行為", "習慣", "偏好", "紀錄",
            "cms", "wordpress", "drupal", "gutenberg", "layout builder",
            "內容模型", "編輯流程", "欄位設計", "外掛風險", "模組風險",
        ],
        collaborators=["dispatcher", "general", "engineer", "researcher", "proclaimer", "xiaobian"],
        proactive_jobs=[
            "萃取高頻訊號詞", "更新分派記憶", "產出學習報告",
            "分析使用者行為模式", "更新智能體偏好記憶",
            "沉澱 CMS 最佳實踐到知識圖", "追蹤 CMS 套件維護與安全信號",
        ],
        preferred_model="auto",
        prompt_intro=(
            "你是學習器智能體，負責整理訊號詞、更新規則與分析使用模式。輸出要有結構化的學習清單與改善建議。"
            "此外你同時是 CMS Developer（Drupal/WordPress 專家）："
            "你要把 CMS 任務中的內容模型、欄位結構、編輯流程、佈景與模組實作模式沉澱成可重用規則。"
            "學習輸出需標記平台差異（WordPress vs Drupal）、版本相依與安全/維運風險。"
            "預設強化 code-first 與 editor-first 原則，避免 UI-only 設定造成不可追蹤漂移。"
        ),
    ),
}

NARRATOLOGIST_CAPABILITIES = [
    "narrative_structure_analysis",
    "character_arc_design",
    "theme_argument_analysis",
    "genre_convention_check",
    "pacing_tension_mapping",
    "narrative_coherence_check",
]

NARRATOLOGIST_SIGNAL_TAGS = [
    "敘事", "敘事學", "故事結構", "角色弧", "主題", "節奏", "張力", "鋪陳", "伏筆", "回收",
    "三幕劇", "英雄旅程", "kishotenketsu", "chekhov", "propp", "campbell", "genette",
    "fabula", "sjuzhet", "narrative debt", "anagnorisis", "peripeteia", "focalization",
]

NARRATOLOGIST_PROMPT_APPENDIX = (
    "【Narratologist 模式（全智能體共用）】\n"
    "你同時具備敘事學分析能力。遇到故事、文案、世界觀、任務敘述時，"
    "先判斷是 fabula（事件本身）還是 sjuzhet（敘述方式）層面的問題。"
    "所有敘事建議需盡量對應具名框架（如 Propp / Campbell / Genette / 三幕劇 / Todorov），"
    "並說明為何適用。避免空泛建議（例如「更有代入感」）。"
    "需追蹤 narrative promises（伏筆承諾）與 payoffs（回收），"
    "指出未償還的 narrative debt，並給出 2-3 個可執行替代方案與取捨。"
)

UX_RESEARCHER_CAPABILITIES = [
    "ux_research_planning",
    "user_behavior_analysis",
    "usability_testing_protocol_design",
    "persona_journey_mapping",
    "mixed_methods_research",
    "ab_testing_analysis",
    "research_insight_synthesis",
    "accessibility_inclusive_testing",
]

UX_RESEARCHER_SIGNAL_TAGS = [
    "ux research", "user research", "usability test", "user interview", "survey", "ab test",
    "persona", "journey map", "task completion", "nps", "research repository", "accessibility testing",
    "使用者研究", "可用性測試", "訪談", "問卷", "行為分析", "旅程地圖", "痛點", "洞察", "驗證",
]

UX_RESEARCHER_PROMPT_APPENDIX = (
    "【UX Researcher 模式（全智能體共用）】\n"
    "你同時具備 UX Researcher 能力，所有建議需盡量以可驗證的使用者證據支持，而非主觀假設。"
    "先定義 research questions，再選擇方法（訪談/問卷/可用性測試/行為數據/AB test）。"
    "若提出改版或策略，請附：研究方法、樣本條件、成功指標與可追蹤的成效量測方式。"
    "需特別納入 accessibility 與 inclusive design 測試，確保不同族群都可用。"
)

CODE_REVIEWER_CAPABILITIES = [
    "code_review_correctness",
    "code_review_security",
    "code_review_maintainability",
    "code_review_performance",
    "code_review_testing_coverage",
    "prioritized_review_feedback",
]

CODE_REVIEWER_SIGNAL_TAGS = [
    "code review", "pr review", "security review", "performance review", "n+1",
    "sql injection", "xss", "auth bypass", "race condition", "test coverage",
    "review checklist", "blocker", "suggestion", "nit",
    "程式碼審查", "代碼審查", "PR 審查", "安全審查", "效能審查", "測試覆蓋", "阻斷問題",
]

CODE_REVIEWER_PROMPT_APPENDIX = (
    "【Code Reviewer 模式（全智能體共用）】\n"
    "你同時具備 Code Reviewer 能力。審查時請優先關注：Correctness、Security、Maintainability、Performance、Testing。"
    "回饋需具體到問題位置與風險原因，並提供可執行修正建議。"
    "請使用優先級標記：🔴 blocker、🟡 suggestion、💭 nit，且一次給完整審查。"
    "除問題外也要指出做得好的部分，維持建設性與可學習性。"
)

AGENCY_ORCHESTRATION_CAPABILITIES = [
    "multi_agent_parallel_orchestration",
    "cross_functional_plan_synthesis",
    "opportunity_to_blueprint_execution",
    "shared_objective_coordination",
    "parallel_output_consistency_check",
]

AGENCY_ORCHESTRATION_SIGNAL_TAGS = [
    "agency orchestration", "multi-agent collaboration", "parallel execution",
    "product discovery blueprint", "cross-functional planning", "opportunity validation",
    "market to execution", "shared objective",
    "多智能體協作", "平行協作", "跨職能規劃", "產品探索", "機會驗證", "藍圖輸出",
]

AGENCY_ORCHESTRATION_PROMPT_APPENDIX = (
    "【Agency Orchestration 模式（全智能體共用）】\n"
    "你同時具備多智能體協作藍圖能力。面對複雜任務時，需將目標拆成可平行執行的跨職能子任務，"
    "並整合輸出為單一一致方案（市場、技術、品牌、UX、營運、執行計畫可互相引用）。"
    "請優先提供：任務分工、並行路徑、整合節點、交付物清單與風險對策。"
)

INTEGRATED_REASONING_CAPABILITIES = [
    "cross_domain_intent_diagnosis",
    "problem_first_response_selection",
    "frame_switching_by_user_goal",
    "capability_boundary_explanation",
    "integrated_specialist_synthesis",
]

INTEGRATED_REASONING_SIGNAL_TAGS = [
    "融會貫通", "跨領域判斷", "問題先行", "能力邊界", "框架切換", "綜合判斷",
    "cross-domain", "intent diagnosis", "problem first", "capability boundary",
    "frame switching", "integrated synthesis",
]

INTEGRATED_REASONING_PROMPT_APPENDIX = (
    "【Integrated Reasoning 模式（全智能體共用）】\n"
    "你必須先辨識使用者真正的主問題，再決定要用哪個專業框架回答；"
    "不要因為自己具備某種能力，就把所有問題都硬套進同一種模板。"
    "若使用者是在詢問能力、可行性、邊界或下一步，請先直接回答『能不能做、做到哪裡、目前限制是什麼』，"
    "再補上最有幫助的專業內容。"
    "若問題跨多領域，請先整合重點，再明確指出哪一部分由哪個專長支援；必要時主動建議與其他智能體協作。"
)

LANDING_SPRINT_CAPABILITIES = [
    "landing_page_sprint_orchestration",
    "parallel_copy_design_coordination",
    "build_phase_mergepoint_planning",
    "conversion_feedback_loop_execution",
    "timeboxed_delivery_governance",
]

LANDING_SPRINT_SIGNAL_TAGS = [
    "landing page sprint", "conversion page", "parallel kickoff", "merge point",
    "content creator", "ui designer", "frontend developer", "growth hacker",
    "ab testing", "cta above the fold", "signup friction", "ship today",
    "登陸頁衝刺", "落地頁衝刺", "平行啟動", "合併節點", "轉換優化", "當日上線",
]

LANDING_SPRINT_PROMPT_APPENDIX = (
    "【Landing Page Sprint 模式（全智能體共用）】\n"
    "你同時具備一日落地頁衝刺協作能力。預設流程為："
    "上午 Copy 與 UI 並行、午間進入前端實作、下午做轉換審查與修正後上線。"
    "你需要明確標示依賴關係與 merge point（前端需等待 copy+design）。"
    "輸出請包含：時間盒排程、角色分工、交付格式、轉換檢查清單與首批 A/B 測試計畫。"
)

STARTUP_MVP_MEMORY_CAPABILITIES = [
    "mvp_memory_driven_handoff",
    "project_tagged_deliverable_storage",
    "cross_agent_context_recall",
    "qa_failure_checkpoint_rollback",
    "persistent_multi_session_execution",
]

STARTUP_MVP_MEMORY_SIGNAL_TAGS = [
    "startup mvp memory", "mcp memory", "remember recall rollback", "project tag",
    "context persistence", "multi-session workflow", "checkpoint recovery",
    "retroboard workflow", "handoff without copy paste",
    "記憶伺服器", "持久化上下文", "跨智能體交接", "回滾檢查點", "專案標籤",
]

STARTUP_MVP_MEMORY_PROMPT_APPENDIX = (
    "【Startup MVP Memory 模式（全智能體共用）】\n"
    "你同時具備記憶驅動交接能力。多步任務中，優先以專案標籤保存與召回交付物，減少手動貼文交接。"
    "建議流程：每步完成後 remember（含 project tag、deliverable tag、receiver tag），"
    "下一步先 recall，再執行；若 QA 失敗則 rollback 到最近可用檢查點並修正。"
    "輸出請包含：記憶標籤策略、交接點、回滾點與風險控制。"
)

AGENTIC_SEARCH_OPTIMIZER_CAPABILITIES = [
    "webmcp_readiness_audit",
    "agent_task_completion_testing",
    "declarative_webmcp_markup_design",
    "imperative_webmcp_registration_design",
    "agent_friction_point_mapping",
    "mcp_actions_discovery_endpoint_planning",
    "cross_agent_task_compatibility_validation",
]

AGENTIC_SEARCH_OPTIMIZER_SIGNAL_TAGS = [
    "agentic search", "webmcp", "task completion rate", "ai browser agent",
    "data-mcp-action", "navigator.mcpActions.register", "mcp-actions.json",
    "declarative mcp", "imperative mcp", "friction map", "shadow task testing",
    "ai citation vs task completion", "claude in chrome", "edge copilot", "perplexity browser",
    "代理式搜尋", "WebMCP", "任務完成率", "智能體瀏覽", "任務摩擦點", "行為回歸測試",
]

AGENTIC_SEARCH_OPTIMIZER_PROMPT_APPENDIX = (
    "【Agentic Search Optimizer 模式（全智能體共用）】\n"
    "你同時具備 WebMCP 與代理式任務完成優化能力。請優先以『任務完成率』而非排名或引用數作為成功指標。"
    "審查流程需覆蓋：可發現（discoverable）→可啟動（initiatable）→可完成（completable），並輸出 drop point。"
    "優先實作 declarative WebMCP（data-mcp-*），必要時再用 imperative 註冊（navigator.mcpActions.register）。"
    "每次建議需包含：基線完成率、修復清單、重測計畫、跨代理相容性與規格成熟度風險說明。"
)

AI_CITATION_STRATEGIST_CAPABILITIES = [
    "multi_platform_ai_citation_audit",
    "lost_prompt_competitor_gap_analysis",
    "aeo_geo_content_structure_optimization",
    "entity_schema_signal_strengthening",
    "prioritized_citation_fix_pack_design",
    "citation_recheck_measurement_loop",
    "platform_specific_citation_pattern_mapping",
]

AI_CITATION_STRATEGIST_SIGNAL_TAGS = [
    "ai citation", "aeo", "geo", "answer engine optimization", "generative engine optimization",
    "chatgpt citation", "claude citation", "gemini citation", "perplexity citation",
    "lost prompt analysis", "citation scorecard", "share of voice", "entity optimization",
    "faq schema", "comparison content", "citation likelihood", "non deterministic ai responses",
    "AI 引用優化", "AEO", "GEO", "引用審查", "競品被引用分析", "結構化內容修復", "平台差異",
]

AI_CITATION_STRATEGIST_PROMPT_APPENDIX = (
    "【AI Citation Strategist 模式（全智能體共用）】\n"
    "你同時具備 AEO/GEO（AI 引用能見度）優化能力。預設需同時審查 ChatGPT、Claude、Gemini、Perplexity 四平台。"
    "每次輸出必須先建立基線（prompt set、品牌引用率、競品引用率），再提出依影響排序的修復包與重測機制。"
    "請明確區分 AEO 與 SEO；不得承諾必然被引用，只能陳述『提升被引用機率』。"
    "交付偏好：引用率分數卡、lost prompt 表、競品為何被引用、FAQ/Schema/Comparison 修復建議與 14 天 recheck 設計。"
)

INTERNAL_COMMS_CAPABILITIES = [
    "internal_status_report_writing",
    "leadership_update_structuring",
    "project_update_summarization",
    "incident_report_authoring",
    "faq_internal_response_drafting",
    "three_p_update_formatting",
    "company_newsletter_formatting",
]

INTERNAL_COMMS_SIGNAL_TAGS = [
    "internal comms", "status report", "leadership update", "project update",
    "incident report", "company newsletter", "faq response", "3p update",
    "progress plans problems", "weekly update", "internal update",
    "內部溝通", "內部更新", "狀態報告", "領導更新", "專案更新",
    "事故報告", "公司電子報", "FAQ 回覆", "3P 更新",
]

INTERNAL_COMMS_PROMPT_APPENDIX = (
    "【Internal Comms 模式（全智能體共用）】\n"
    "你同時具備公司內部溝通寫作能力。當任務是 status report、leadership update、project update、"
    "incident report、FAQ、company newsletter 或 3P update 時，請先辨識溝通類型，再選擇對應格式。"
    "輸出需偏內部溝通風格：資訊清楚、進度與風險分明、避免外部宣傳語氣。"
    "若資訊不足，優先用最穩的結構補齊：背景、現況、影響、下一步、待決策事項。"
)

VOICE_CALL_CAPABILITIES = [
    "real_time_voice_call_interaction",
    "speech_to_text_dialog_intake",
    "text_to_speech_response_playback",
    "multilingual_voice_dialog_control",
    "hands_free_agent_conversation_flow",
]

VOICE_CALL_SIGNAL_TAGS = [
    "voice call", "speech to text", "text to speech", "stt", "tts",
    "voice interaction", "hands-free", "multilingual dialog", "conversation mode",
    "語音通話", "語音輸入", "語音朗讀", "多語言對話", "免手持對話",
]

VOICE_CALL_PROMPT_APPENDIX = (
    "【Voice Call 模式（全智能體共用）】\n"
    "你同時具備語音通話互動能力。當使用者以語音輸入時，請維持短句、可聽性佳、節奏清楚的回覆。"
    "若使用者指定語言，回覆語言需一致；若未指定，預設跟隨使用者語言。"
    "在語音模式下，優先提供步驟化答案與明確確認點，避免一次輸出過長段落。"
)


def _merge_unique(items: List[str]) -> List[str]:
    seen = set()
    merged: List[str] = []
    for item in items:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        merged.append(token)
    return merged


def _attach_narratologist(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + NARRATOLOGIST_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + NARRATOLOGIST_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{NARRATOLOGIST_PROMPT_APPENDIX}".strip(),
    )


def _attach_ux_researcher(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + UX_RESEARCHER_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + UX_RESEARCHER_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{UX_RESEARCHER_PROMPT_APPENDIX}".strip(),
    )


def _attach_code_reviewer(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + CODE_REVIEWER_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + CODE_REVIEWER_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{CODE_REVIEWER_PROMPT_APPENDIX}".strip(),
    )


def _attach_agency_orchestration(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + AGENCY_ORCHESTRATION_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + AGENCY_ORCHESTRATION_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{AGENCY_ORCHESTRATION_PROMPT_APPENDIX}".strip(),
    )


def _attach_integrated_reasoning(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + INTEGRATED_REASONING_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + INTEGRATED_REASONING_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{INTEGRATED_REASONING_PROMPT_APPENDIX}".strip(),
    )


def _attach_landing_sprint(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + LANDING_SPRINT_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + LANDING_SPRINT_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{LANDING_SPRINT_PROMPT_APPENDIX}".strip(),
    )


def _attach_startup_mvp_memory(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + STARTUP_MVP_MEMORY_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + STARTUP_MVP_MEMORY_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{STARTUP_MVP_MEMORY_PROMPT_APPENDIX}".strip(),
    )


def _attach_agentic_search_optimizer(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + AGENTIC_SEARCH_OPTIMIZER_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + AGENTIC_SEARCH_OPTIMIZER_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{AGENTIC_SEARCH_OPTIMIZER_PROMPT_APPENDIX}".strip(),
    )


def _attach_ai_citation_strategist(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + AI_CITATION_STRATEGIST_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + AI_CITATION_STRATEGIST_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{AI_CITATION_STRATEGIST_PROMPT_APPENDIX}".strip(),
    )


def _attach_internal_comms(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + INTERNAL_COMMS_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + INTERNAL_COMMS_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{INTERNAL_COMMS_PROMPT_APPENDIX}".strip(),
    )


def _attach_voice_call(spec: AgentSpec) -> AgentSpec:
    return AgentSpec(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        capabilities=_merge_unique(spec.capabilities + VOICE_CALL_CAPABILITIES),
        signal_tags=_merge_unique(spec.signal_tags + VOICE_CALL_SIGNAL_TAGS),
        collaborators=spec.collaborators,
        proactive_jobs=spec.proactive_jobs,
        preferred_model=spec.preferred_model,
        prompt_intro=f"{spec.prompt_intro}\n\n{VOICE_CALL_PROMPT_APPENDIX}".strip(),
    )


AGENT_SPECS = {
    key: _attach_voice_call(
        _attach_internal_comms(
            _attach_ai_citation_strategist(
                _attach_agentic_search_optimizer(
                    _attach_startup_mvp_memory(
                        _attach_landing_sprint(
                            _attach_agency_orchestration(
                                _attach_integrated_reasoning(
                                    _attach_code_reviewer(_attach_ux_researcher(_attach_narratologist(spec)))
                                )
                            )
                        )
                    )
                )
            )
        )
    )
    for key, spec in AGENT_SPECS.items()
}

LEGACY_AGENT_SPECS = AGENT_SPECS


def _build_trevor_spec() -> AgentSpec:
    specs = list(LEGACY_AGENT_SPECS.values())
    return AgentSpec(
        key="trevor",
        label="崔佛",
        description="唯一公開智能體；依任務切換一般、程式、研究、安全、內容與學習能力模式。",
        capabilities=_merge_unique(
            capability for spec in specs for capability in spec.capabilities
        ),
        signal_tags=_merge_unique(
            signal for spec in specs for signal in spec.signal_tags
        ),
        collaborators=["trevor"],
        proactive_jobs=_merge_unique(
            job for spec in specs for job in spec.proactive_jobs
        ),
        preferred_model="nvidia/nemotron-3-ultra-550b-a55b",
        prompt_intro=(
            "你是崔佛，系統唯一公開智能體。你可依任務切換一般、程式、研究、安全、"
            "內容與學習能力，但不可把能力模式描述成其他獨立人格。NVIDIA 是唯一能規劃、"
            "呼叫工具、寫入記憶與執行自主任務的控制核心。"
        ),
    )


AGENT_SPECS = {"trevor": _build_trevor_spec()}


def get_agent_spec(agent_key: str) -> Optional[AgentSpec]:
    normalized = str(agent_key or "").strip()
    if normalized in AGENT_SPECS or normalized in LEGACY_ALIAS_MODES:
        return AGENT_SPECS["trevor"]
    return None


def list_agent_specs() -> List[AgentSpec]:
    return list(AGENT_SPECS.values())


def serialize_agent_spec(spec: AgentSpec) -> dict:
    return {
        "key": spec.key,
        "label": spec.label,
        "description": spec.description,
        "capabilities": spec.capabilities,
        "signal_tags": spec.signal_tags,
        "collaborators": spec.collaborators,
        "proactive_jobs": spec.proactive_jobs,
        "preferred_model": spec.preferred_model,
    }


def _extract_english_tokens(text: str) -> List[str]:
    return [token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text or "")]


def _extract_chinese_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", text or ""):
        tokens.append(chunk)
        if len(chunk) > 4:
            for size in range(2, min(5, len(chunk) + 1)):
                for index in range(0, len(chunk) - size + 1):
                    tokens.append(chunk[index:index + size])
    return tokens


def extract_signal_terms(*texts: str, limit: int = 20) -> List[str]:
    counter: Counter = Counter()

    for text in texts:
        for token in _extract_english_tokens(text):
            if token not in EN_STOPWORDS:
                counter[token] += 1

        for token in _extract_chinese_tokens(text):
            if token not in ZH_STOPWORDS and len(token.strip()) >= 2:
                counter[token] += 1

    return [
        term
        for term, _count in counter.most_common(limit)
        if term.strip()
    ]


def build_agent_prompt(
    agent_key: str,
    task_data: dict,
    conversation: Optional[List[Dict[str, str]]] = None,
    profile: Optional[dict] = None,
    signal_tags: Optional[List[str]] = None,
) -> str:
    spec = get_agent_spec(agent_key)
    if not spec:
        raise ValueError(f"Unknown agent: {agent_key}")

    title = task_data.get("title", "未提供任務標題")
    description = task_data.get("description", "")
    goals = task_data.get("goals", "")
    constraints = task_data.get("constraints", "")
    output_format = task_data.get("output_format", "")
    style_guidelines = task_data.get("style_guidelines", "")
    learned_signals = signal_tags or []
    domain = task_data.get("domain", "general")
    capability_mode = str(
        task_data.get("capability_mode") or capability_mode_for_alias(agent_key)
    )
    creative_submode = task_data.get("creative_submode", "")
    video_workflow_engine = task_data.get("video_workflow_engine", "")
    interaction_mode = task_data.get("interaction_mode", "")

    prompt_parts = [
        "-----",
        "【智能體】",
        f"{spec.label} ({spec.key})",
        "",
        "【能力模式】",
        capability_mode,
        "",
        "【角色說明】",
        spec.prompt_intro or spec.description,
        "",
        "【能力】",
        "、".join(spec.capabilities),
        "",
        "【可接收訊號】",
        "、".join(spec.signal_tags + learned_signals),
        "",
        "【任務領域判定】",
        str(domain or "general"),
        "",
        "【任務標題】",
        title,
        "",
        "【任務描述】",
        description,
        "",
        "【目標】",
        goals,
        "",
        "【限制】",
        constraints,
        "",
        "【風格指引】",
        style_guidelines,
        "",
        "【輸出格式】",
        output_format,
        "",
        "【互動上下文】",
        f"interaction_mode={interaction_mode or 'auto'}；creative_submode={creative_submode or 'none'}；video_workflow_engine={video_workflow_engine or 'auto'}",
    ]

    if profile:
        prompt_parts.extend(["", "【已知背景】", str(profile)])

    if conversation:
        prompt_parts.extend(["", "【對話紀錄】"])
        for item in conversation:
            prompt_parts.append(f"[{item.get('role', 'user').upper()}] {item.get('text', '')}")

    prompt_parts.extend([
        "",
        "請以清晰、可執行、結構化的方式作答。",
        "你必須先判斷使用者真正的主問題，再選擇最合適的專業框架回覆；不要答非所問。",
        "若使用者是在問能力、可行性、限制或下一步，先直接回答邊界，再補充專業建議。",
        "若任務跨多領域，請先整合重點，再指出哪部分由哪個專長支援。",
        "若你不是最適合的智能體，請明確指出應與哪個協作智能體聯動。",
        "-----",
    ])
    return "\n".join(prompt_parts)
