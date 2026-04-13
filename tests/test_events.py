import pytest
from beatsaber.track import (
    BSEvent,
    BSChannel,
    EventType,
    LightValue,
    BLUE_FLASH_DURATION,
    BLUE_FADE_DURATION,
    RED_FLASH_DURATION,
    RED_FADE_DURATION,
)


class TestBSEvent:
    """Tests for BSEvent comparison operators."""

    def test_lt_with_int(self):
        event = BSEvent(EventType.BACK_LASERS, 1000, 1)
        assert event < 2000
        assert not event < 500

    def test_lt_with_event(self):
        event1 = BSEvent(EventType.BACK_LASERS, 1000, 1)
        event2 = BSEvent(EventType.BACK_LASERS, 2000, 1)
        assert event1 < event2
        assert not event2 < event1

    def test_ge_with_int(self):
        event = BSEvent(EventType.BACK_LASERS, 1000, 1)
        assert event >= 1000  # Same time - should be True
        assert event >= 500
        assert not event >= 2000

    def test_ge_with_event(self):
        event1 = BSEvent(EventType.BACK_LASERS, 1000, 1)
        event2 = BSEvent(EventType.BACK_LASERS, 1000, 1)
        event3 = BSEvent(EventType.BACK_LASERS, 2000, 1)
        assert event1 >= event2  # Same time - should be True
        assert not event1 >= event3

    def test_repr(self):
        event = BSEvent(EventType.BACK_LASERS, 1000, 1)
        repr_str = repr(event)
        assert "BACK_LASERS" in repr_str
        assert "1000" in repr_str


class TestBSChannel:
    """Tests for BSChannel get_value method."""

    @pytest.fixture
    def light_channel(self):
        channel = BSChannel(EventType.ROAD_LIGHTS)
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 0, LightValue.OFF.value))
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 1000, LightValue.BLUE_ON.value))
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 2000, LightValue.RED_ON.value))
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 3000, LightValue.BLUE_FLASH.value))
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 4000, LightValue.BLUE_FADE.value))
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 5000, LightValue.RED_FLASH.value))
        channel.add_event(BSEvent(EventType.ROAD_LIGHTS, 6000, LightValue.RED_FADE.value))
        channel.sort()
        return channel

    @pytest.fixture
    def ring_zoom_channel(self):
        channel = BSChannel(EventType.RINGS_ZOOM)
        channel.add_event(BSEvent(EventType.RINGS_ZOOM, 0, 0))
        channel.add_event(BSEvent(EventType.RINGS_ZOOM, 1000, 1))
        channel.sort()
        return channel

    @pytest.fixture
    def ring_rotate_channel(self):
        channel = BSChannel(EventType.RINGS_ROTATE)
        channel.add_event(BSEvent(EventType.RINGS_ROTATE, 0, 0))
        channel.add_event(BSEvent(EventType.RINGS_ROTATE, 1000, 0))
        channel.sort()
        return channel

    def test_empty_channel(self):
        channel = BSChannel(EventType.ROAD_LIGHTS)
        color, time = channel.get_value(500)
        # Empty channels return (0, 0) by design
        assert color == 0
        assert time == 0

    def test_light_off(self, light_channel):
        color, time = light_channel.get_value(500)
        assert color == (0, 0, 0, 0)

    def test_light_blue_on(self, light_channel):
        color, time = light_channel.get_value(1500)
        assert color == (0, 0, 1, 1)

    def test_light_red_on(self, light_channel):
        color, time = light_channel.get_value(2500)
        assert color == (1, 0, 0, 1)

    def test_light_blue_flash(self, light_channel):
        # At the start of flash, brightness should be 1.0
        color, time = light_channel.get_value(3000)
        assert color == (0, 0, 1.0, 1)
        # Halfway through flash
        color, time = light_channel.get_value(3000 + BLUE_FLASH_DURATION // 2)
        assert color[2] == pytest.approx(0.5, abs=0.01)

    def test_light_blue_fade(self, light_channel):
        color, time = light_channel.get_value(4000)
        assert color == (0, 0, 1.0, 1)

    def test_light_red_flash(self, light_channel):
        color, time = light_channel.get_value(5000)
        assert color == (1.0, 0, 0, 1)

    def test_light_red_fade(self, light_channel):
        color, time = light_channel.get_value(6000)
        assert color == (1.0, 0, 0, 1)

    def test_ring_zoom_interpolation(self, ring_zoom_channel):
        # After fix, interpolation should work correctly
        time, value = ring_zoom_channel.get_value(0)
        assert value == 0
        # Halfway between events at 0 and 1000
        time, value = ring_zoom_channel.get_value(500)
        assert value == pytest.approx(0.5, abs=0.01)
        # Near the end
        time, value = ring_zoom_channel.get_value(900)
        assert value == pytest.approx(0.9, abs=0.01)

    def test_ring_zoom_division_by_zero_protection(self):
        """Test that events with same timestamp don't cause division by zero."""
        channel = BSChannel(EventType.RINGS_ZOOM)
        channel.add_event(BSEvent(EventType.RINGS_ZOOM, 1000, 0))
        channel.add_event(BSEvent(EventType.RINGS_ZOOM, 1000, 1))  # Same time!
        channel.sort()
        # Should not raise and should return 0
        time, value = channel.get_value(1000)
        assert value == 0

    def test_ring_rotate(self, ring_rotate_channel):
        time, value = ring_rotate_channel.get_value(500)
        assert time == 0
        assert value == 0

    def test_time_before_first_event(self, light_channel):
        """Test querying time before any events exist."""
        color, time = light_channel.get_value(-100)
        assert color == (0, 0, 0, 0)

    def test_flash_fade_values_clamped(self, light_channel):
        """Test that flash/fade values don't go negative when past duration."""
        # Query blue flash well past its duration (at time 5000, flash started at 3000)
        # Duration is 500ms, so at 5000ms it's 2000ms past the flash
        color, time = light_channel.get_value(10000)
        # Blue channel should be clamped to 0, not negative
        assert color[2] >= 0
        # Same for red fade - query well past duration
        color, time = light_channel.get_value(15000)
        assert color[0] >= 0


class TestConstants:
    """Test that constants are reasonable values."""

    def test_flash_durations_are_positive(self):
        assert BLUE_FLASH_DURATION > 0
        assert RED_FLASH_DURATION > 0

    def test_fade_durations_are_positive(self):
        assert BLUE_FADE_DURATION > 0
        assert RED_FADE_DURATION > 0

    def test_fade_longer_than_flash(self):
        # Fades should be slower/longer than flashes
        assert BLUE_FADE_DURATION > BLUE_FLASH_DURATION
        assert RED_FADE_DURATION > RED_FLASH_DURATION
