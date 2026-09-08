import unittest

from scripts.transcript_insights.create_sync_flow import (
    BATCH,
    build_definition,
)


class SyncFlowDrainLoopTests(unittest.TestCase):
    def test_drain_signal_uses_rows_fetched_not_processed_count(self) -> None:
        """RowsFetched counts every row the query returned; TranscriptsProcessed only counts
        rows that synced without error. Comparing the loop's drain signal against the success
        count would let a single mid-batch failure masquerade as a short (final) batch and stop
        the loop while a full backlog remains."""
        definition = build_definition("Hour", 1)
        record_batch_size = definition["actions"]["Until_backlog_drained"]["actions"]["Record_batch_size"]

        self.assertEqual(
            "@body('Sync_transcripts')?['RowsFetched']",
            record_batch_size["inputs"]["value"],
        )
        self.assertNotIn("TranscriptsProcessed", record_batch_size["inputs"]["value"])

    def test_batch_size_consistent_across_variable_query_and_loop_condition(self) -> None:
        definition = build_definition("Hour", 1)
        until_loop = definition["actions"]["Until_backlog_drained"]
        sync_action = until_loop["actions"]["Sync_transcripts"]
        initial_value = definition["actions"]["Initialise_batch_counter"]["inputs"]["variables"][0]["value"]

        self.assertEqual(BATCH, initial_value)
        self.assertEqual(BATCH, sync_action["inputs"]["parameters"]["item/MaxRecords"])
        self.assertEqual(f"@less(variables('LastProcessed'), {BATCH})", until_loop["expression"])

    def test_loop_bounded_to_twelve_batches_per_trigger(self) -> None:
        definition = build_definition("Hour", 1)
        self.assertEqual(12, definition["actions"]["Until_backlog_drained"]["limit"]["count"])


if __name__ == "__main__":
    unittest.main()
