using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PvciTranscripts
{
    /// <summary>
    /// Minimal JSON reader. Deliberately dependency-free so the plugin assembly needs no
    /// NuGet payload and raises no sandbox assembly-load questions.
    /// Produces: Dictionary&lt;string,object&gt;, List&lt;object&gt;, string, double, bool, null.
    /// </summary>
    internal static class Json
    {
        public static object Parse(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return null;
            int i = 0;
            object value = ParseValue(text, ref i);
            return value;
        }

        private static void SkipWs(string s, ref int i)
        {
            while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++;
        }

        private static object ParseValue(string s, ref int i)
        {
            SkipWs(s, ref i);
            if (i >= s.Length) return null;

            char c = s[i];
            switch (c)
            {
                case '{': return ParseObject(s, ref i);
                case '[': return ParseArray(s, ref i);
                case '"': return ParseString(s, ref i);
                case 't': i += 4; return true;
                case 'f': i += 5; return false;
                case 'n': i += 4; return null;
                default: return ParseNumber(s, ref i);
            }
        }

        private static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            var result = new Dictionary<string, object>(StringComparer.Ordinal);
            i++; // {
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; return result; }

            while (i < s.Length)
            {
                SkipWs(s, ref i);
                if (i >= s.Length || s[i] != '"') break;
                string key = ParseString(s, ref i);
                SkipWs(s, ref i);
                if (i < s.Length && s[i] == ':') i++;
                result[key] = ParseValue(s, ref i);
                SkipWs(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == '}') { i++; break; }
                break;
            }
            return result;
        }

        private static List<object> ParseArray(string s, ref int i)
        {
            var result = new List<object>();
            i++; // [
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; return result; }

            while (i < s.Length)
            {
                result.Add(ParseValue(s, ref i));
                SkipWs(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == ']') { i++; break; }
                break;
            }
            return result;
        }

        private static string ParseString(string s, ref int i)
        {
            var sb = new StringBuilder();
            i++; // opening quote
            while (i < s.Length)
            {
                char c = s[i++];
                if (c == '"') break;
                if (c != '\\') { sb.Append(c); continue; }

                if (i >= s.Length) break;
                char esc = s[i++];
                switch (esc)
                {
                    case 'n': sb.Append('\n'); break;
                    case 't': sb.Append('\t'); break;
                    case 'r': sb.Append('\r'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case '/': sb.Append('/'); break;
                    case '\\': sb.Append('\\'); break;
                    case '"': sb.Append('"'); break;
                    case 'u':
                        if (i + 4 <= s.Length)
                        {
                            int code = int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                            sb.Append((char)code);
                            i += 4;
                        }
                        break;
                    default: sb.Append(esc); break;
                }
            }
            return sb.ToString();
        }

        private static object ParseNumber(string s, ref int i)
        {
            int start = i;
            while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '-' || s[i] == '+' || s[i] == '.' || s[i] == 'e' || s[i] == 'E')) i++;
            string raw = s.Substring(start, i - start);
            double d;
            return double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out d) ? (object)d : null;
        }

        public static string Write(object value)
        {
            var sb = new StringBuilder();
            WriteValue(sb, value, 0);
            return sb.ToString();
        }

        private static void WriteValue(StringBuilder sb, object v, int depth)
        {
            string pad = new string(' ', depth * 2);
            string padIn = new string(' ', (depth + 1) * 2);

            if (v == null) { sb.Append("null"); return; }
            if (v is bool) { sb.Append(((bool)v) ? "true" : "false"); return; }
            if (v is double)
            {
                double d = (double)v;
                sb.Append(d == Math.Floor(d) && !double.IsInfinity(d)
                    ? ((long)d).ToString(CultureInfo.InvariantCulture)
                    : d.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (v is int || v is long) { sb.Append(Convert.ToInt64(v).ToString(CultureInfo.InvariantCulture)); return; }
            if (v is string) { WriteString(sb, (string)v); return; }

            var dict = v as Dictionary<string, object>;
            if (dict != null)
            {
                if (dict.Count == 0) { sb.Append("{}"); return; }
                sb.Append("{\n");
                int n = 0;
                foreach (var kv in dict)
                {
                    sb.Append(padIn);
                    WriteString(sb, kv.Key);
                    sb.Append(": ");
                    WriteValue(sb, kv.Value, depth + 1);
                    if (++n < dict.Count) sb.Append(',');
                    sb.Append('\n');
                }
                sb.Append(pad).Append('}');
                return;
            }

            var list = v as List<object>;
            if (list != null)
            {
                if (list.Count == 0) { sb.Append("[]"); return; }
                sb.Append("[\n");
                for (int i = 0; i < list.Count; i++)
                {
                    sb.Append(padIn);
                    WriteValue(sb, list[i], depth + 1);
                    if (i < list.Count - 1) sb.Append(',');
                    sb.Append('\n');
                }
                sb.Append(pad).Append(']');
                return;
            }

            WriteString(sb, v.ToString());
        }

        private static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        // Convenience accessors -------------------------------------------------

        public static Dictionary<string, object> Obj(object v) { return v as Dictionary<string, object>; }

        public static List<object> Arr(object v) { return v as List<object>; }

        public static object Get(object v, string key)
        {
            var d = v as Dictionary<string, object>;
            object result;
            return d != null && d.TryGetValue(key, out result) ? result : null;
        }

        public static string Str(object v, string key)
        {
            object o = Get(v, key);
            return o as string;
        }

        public static int? Int(object v, string key)
        {
            object o = Get(v, key);
            if (o is double) return (int)(double)o;
            if (o is string)
            {
                int parsed;
                if (int.TryParse((string)o, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed)) return parsed;
            }
            return null;
        }

        public static long? Long(object v, string key)
        {
            object o = Get(v, key);
            if (o is double) return (long)(double)o;
            if (o is string)
            {
                long parsed;
                if (long.TryParse((string)o, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed)) return parsed;
            }
            return null;
        }
    }
}
