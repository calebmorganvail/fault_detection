"""Server side synchronization of the two live sensor streams.

The bug this fixes
------------------
In v1 each Pi POSTed on its own schedule and the server appended every
reading to one shared list. The dashboard then compared "the last two
readings" and called that a pair. Because the two Pis were never in
lockstep, network jitter meant the dashboard regularly compared an A
reading against a B reading from a different moment in time, which
showed up as fake divergence spikes. This got flagged during the OS
demo.

The fix
-------
Readings go into a buffer keyed by a one second time bucket. A bucket is
only released to the dashboard once BOTH sensors have reported for it,
so the dashboard never sees a mismatched pair. If a partner never shows
up, the bucket is dropped after TIMEOUT_SECONDS so one disconnected
sensor cannot stall the chart forever.
"""

from datetime import datetime

BUCKET_SECONDS = 1
TIMEOUT_SECONDS = 3


class Synchronizer:
    """Buffers readings until both sensors have reported for a bucket."""

    def __init__(self, bucket_seconds=BUCKET_SECONDS, timeout_seconds=TIMEOUT_SECONDS):
        self.bucket_seconds = bucket_seconds
        self.timeout_seconds = timeout_seconds

        # bucket key -> {"A": reading, "B": reading}
        self.buffer = {}

        # Counters, handy for the status endpoint and the demo.
        self.synced_count = 0
        self.dropped_count = 0

    def bucket_key(self, timestamp):
        """Round an ISO timestamp down to the start of its bucket."""
        moment = datetime.fromisoformat(timestamp)
        moment = moment.replace(microsecond=0)
        moment = moment.replace(second=moment.second - moment.second % self.bucket_seconds)
        return moment.isoformat()

    def add(self, reading):
        """Buffer a reading.

        Returns a synced pair once both sensors have reported for that
        bucket, otherwise None (the reading is still buffered).
        """
        key = self.bucket_key(reading["timestamp"])
        bucket = self.buffer.setdefault(key, {})
        bucket[reading["sensor_id"]] = reading

        if "A" in bucket and "B" in bucket:
            del self.buffer[key]
            self.synced_count += 1
            return {"timestamp": key, "a": bucket["A"], "b": bucket["B"]}

        return None

    def drop_stale(self, now):
        """Throw away buckets whose partner never arrived.

        `now` is a datetime. Returns how many buckets were dropped.
        """
        dropped = 0

        for key in list(self.buffer):
            age = (now - datetime.fromisoformat(key)).total_seconds()
            if age > self.timeout_seconds:
                del self.buffer[key]
                dropped += 1

        self.dropped_count += dropped
        return dropped

    def pending(self):
        """How many buckets are still waiting on a partner."""
        return len(self.buffer)
