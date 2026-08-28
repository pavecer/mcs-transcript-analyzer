using System;
using System.Collections.Generic;
using System.IO;
using PvciTranscripts;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length != 1)
        {
            Console.Error.WriteLine("Usage: TranscriptParityHarness <fixture.json>");
            return 2;
        }

        object fixture = Json.Parse(File.ReadAllText(args[0]));
        List<object> activities = Json.Arr(Json.Get(fixture, "activities")) ?? new List<object>();
        TranscriptDiagnostics diagnostics = TranscriptAnalysis.ExtractDiagnostics(activities);
        var output = new Dictionary<string, object>(StringComparer.Ordinal)
        {
            {
                "diagnostics",
                new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    { "topic_id", diagnostics.TopicId },
                    { "topic_name", diagnostics.TopicName },
                    { "user_error_count", diagnostics.UserErrorCount },
                    { "primary_error_code", diagnostics.PrimaryErrorCode },
                    { "primary_error_message", diagnostics.PrimaryErrorMessage },
                    { "primary_error_topic", diagnostics.PrimaryErrorTopic },
                    { "error_category", diagnostics.ErrorCategory },
                    {
                        "user_error_reason",
                        TranscriptAnalysis.ErrorReason(
                            diagnostics.PrimaryErrorCode,
                            diagnostics.PrimaryErrorMessage)
                    },
                }
            },
            { "knowledge_calls", TranscriptAnalysis.ExtractKnowledgeCalls(activities) },
        };
        Console.WriteLine(Json.Write(output));
        return 0;
    }
}
