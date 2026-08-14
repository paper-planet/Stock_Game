#market clock
import asyncio


class MarketClock:

    def __init__(self):

        self.hour = 9
        self.minute = 30

        self.open_hour = 9
        self.open_minute = 30

        self.close_hour = 16
        self.close_minute = 0

        self.running = False

    @property
    def time_string(self):

        suffix = "AM"

        hour = self.hour

        if hour >= 12:
            suffix = "PM"

        display_hour = hour

        if display_hour > 12:
            display_hour -= 12

        return (
            f"{display_hour}:"
            f"{self.minute:02d} "
            f"{suffix}"
        )

    @property
    def is_open(self):

        current = (
            self.hour * 60
            + self.minute
        )

        opening = (
            self.open_hour * 60
            + self.open_minute
        )

        closing = (
            self.close_hour * 60
            + self.close_minute
        )

        return (
            opening
            <= current
            < closing
        )

    def advance_minute(self):

        self.minute += 1

        if self.minute >= 60:

            self.minute = 0
            self.hour += 1

    def next_day(self):

        self.hour = 9
        self.minute = 30

    async def tick(self):

        await asyncio.sleep(
            0.08
        )

        self.advance_minute()