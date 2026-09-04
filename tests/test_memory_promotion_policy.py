from core.memory_policy import MemoryPromotionPolicy


def test_only_durable_or_explicit_information_is_promoted():
    policy = MemoryPromotionPolicy()

    assert policy.assess("你好").promote is False
    assert policy.assess("今天天氣如何").promote is False
    assert policy.assess("請記住我偏好繁體中文").promote is True
    assert policy.assess("之後回答都先講結論").promote is True
    assert policy.assess("我們決定採用單一聊天入口").promote is True
    assert policy.assess("目前長期目標是把崔佛重構成可用智能體").promote is True
    assert policy.assess("這個程式必須先修好才能測試").promote is False
    assert policy.assess("以後你必須先區分對話和執行").promote is True


def test_long_term_retrieval_requires_a_cross_session_signal():
    policy = MemoryPromotionPolicy()

    assert policy.should_retrieve("你好") is False
    assert policy.should_retrieve("解釋依附理論") is False
    assert policy.should_retrieve("繼續我們之前的重構") is True
    assert policy.should_retrieve("照原本決定的方式處理") is True


def test_unconfirmed_sensitive_inference_is_not_promoted():
    decision = MemoryPromotionPolicy().assess("我覺得電視好像在對我說話")

    assert decision.promote is False
    assert decision.sensitive
