from core.safety_signals import SafetySignalTracker


def test_weak_single_signal_does_not_label_or_warn():
    tracker = SafetySignalTracker()
    result = tracker.assess("s1", "我最近責任感有點高")

    assert not result.should_nudge
    assert result.diagnosis == ""


def test_direct_referential_signal_uses_non_diagnostic_nudge():
    tracker = SafetySignalTracker()
    result = tracker.assess("s1", "我覺得新聞裡的資訊都在專門對我說話")

    assert result.should_nudge
    assert "感受" in result.nudge
    assert "診斷" not in result.nudge
    assert result.diagnosis == ""


def test_repeated_mission_signals_raise_a_nudge_within_one_session_only():
    tracker = SafetySignalTracker()

    first = tracker.assess("s1", "我好像有一個很大的使命")
    second = tracker.assess("s1", "而且只有我能完成這個使命")
    other = tracker.assess("s2", "我最近責任感有點高")

    assert not first.should_nudge
    assert second.should_nudge
    assert not other.should_nudge
