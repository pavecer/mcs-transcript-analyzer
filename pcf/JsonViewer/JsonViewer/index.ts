import { IInputs, IOutputs } from "./generated/ManifestTypes";

type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
interface NodeRef {
    path: string;
    key: string | null;
    value: Json;
    depth: number;
}

const MAX_INLINE_STRING = 400;

export class JsonViewer implements ComponentFramework.StandardControl<IInputs, IOutputs> {
    private root!: HTMLDivElement;
    private body!: HTMLDivElement;
    private stat!: HTMLSpanElement;
    private searchBox!: HTMLInputElement;
    private rawBtn!: HTMLButtonElement;

    private parsed: Json = null;
    private parseError: string | null = null;
    private rawText = "";
    private collapsed = new Set<string>();
    private filter = "";
    private rawMode = false;
    private autoDepth = 2;

    public init(
        context: ComponentFramework.Context<IInputs>,
        _notifyOutputChanged: () => void,
        _state: ComponentFramework.Dictionary,
        container: HTMLDivElement
    ): void {
        this.autoDepth = context.parameters.startCollapsedDepth?.raw ?? 2;

        this.root = document.createElement("div");
        this.root.className = "pvci-json";
        this.root.style.height = `${context.parameters.viewerHeight?.raw || 460}px`;

        const bar = document.createElement("div");
        bar.className = "pvci-json__bar";

        const mkBtn = (text: string, title: string, onClick: () => void): HTMLButtonElement => {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = text;
            b.title = title;
            b.addEventListener("click", onClick);
            bar.appendChild(b);
            return b;
        };

        mkBtn("Expand all", "Expand every node", () => {
            this.collapsed.clear();
            this.render();
        });
        mkBtn("Collapse all", "Collapse every node", () => {
            this.collapseAll(0);
            this.render();
        });
        this.rawBtn = mkBtn("Raw", "Toggle raw text", () => {
            this.rawMode = !this.rawMode;
            this.rawBtn.setAttribute("aria-pressed", String(this.rawMode));
            this.render();
        });
        this.rawBtn.setAttribute("aria-pressed", "false");
        mkBtn("Copy", "Copy JSON to clipboard", () => {
            void navigator.clipboard?.writeText(this.rawText);
        });

        this.searchBox = document.createElement("input");
        this.searchBox.className = "pvci-json__search";
        this.searchBox.type = "search";
        this.searchBox.placeholder = "Filter keys and values…";
        this.searchBox.addEventListener("input", () => {
            this.filter = this.searchBox.value.trim().toLowerCase();
            this.render();
        });
        bar.appendChild(this.searchBox);

        this.stat = document.createElement("span");
        this.stat.className = "pvci-json__stat";
        bar.appendChild(this.stat);

        this.body = document.createElement("div");
        this.body.className = "pvci-json__body";

        this.root.appendChild(bar);
        this.root.appendChild(this.body);
        container.appendChild(this.root);
    }

    public updateView(context: ComponentFramework.Context<IInputs>): void {
        const next = context.parameters.jsonValue?.raw ?? "";
        if (next !== this.rawText) {
            this.rawText = next;
            this.parse();
            this.collapseAll(this.autoDepth);
        }
        this.root.style.height = `${context.parameters.viewerHeight?.raw || 460}px`;
        this.render();
    }

    private parse(): void {
        this.parseError = null;
        this.parsed = null;
        const text = this.rawText.trim();
        if (!text) return;
        try {
            this.parsed = JSON.parse(text) as Json;
        } catch (e) {
            this.parseError = e instanceof Error ? e.message : String(e);
        }
    }

    /** Collapse containers at or below `depth` so large payloads open instantly. */
    private collapseAll(depth: number): void {
        this.collapsed.clear();
        const walk = (value: Json, path: string, d: number): void => {
            if (!isContainer(value)) return;
            if (d >= depth) this.collapsed.add(path);
            entriesOf(value).forEach(([k, v]) => walk(v, `${path}/${k}`, d + 1));
        };
        walk(this.parsed, "$", 0);
    }

    private render(): void {
        this.body.textContent = "";

        if (this.parseError) {
            const d = document.createElement("div");
            d.className = "pvci-json__error";
            d.textContent = `Not valid JSON — showing raw text.\n${this.parseError}`;
            this.body.appendChild(d);
            this.appendRaw();
            this.stat.textContent = `${this.rawText.length.toLocaleString()} chars`;
            return;
        }

        if (!this.rawText.trim()) {
            const d = document.createElement("div");
            d.className = "pvci-json__empty";
            d.textContent = "No content.";
            this.body.appendChild(d);
            this.stat.textContent = "";
            return;
        }

        if (this.rawMode) {
            this.appendRaw();
            this.stat.textContent = `${this.rawText.length.toLocaleString()} chars`;
            return;
        }

        const counts = { nodes: 0, shown: 0 };
        this.renderNode({ path: "$", key: null, value: this.parsed, depth: 0 }, this.body, counts);

        const size = `${this.rawText.length.toLocaleString()} chars`;
        this.stat.textContent = this.filter
            ? `${counts.shown.toLocaleString()} match / ${counts.nodes.toLocaleString()} nodes · ${size}`
            : `${counts.nodes.toLocaleString()} nodes · ${size}`;
    }

    private appendRaw(): void {
        const pre = document.createElement("pre");
        pre.className = "pvci-json__raw";
        pre.textContent = this.rawText;
        this.body.appendChild(pre);
    }

    private renderNode(node: NodeRef, host: HTMLElement, counts: { nodes: number; shown: number }): boolean {
        counts.nodes++;
        const container = isContainer(node.value);
        const isCollapsed = container && this.collapsed.has(node.path);

        const row = document.createElement("div");
        row.className = "pvci-json__row";
        row.style.paddingLeft = `${node.depth * 14}px`;

        const toggle = document.createElement("span");
        toggle.className = container ? "pvci-json__toggle" : "pvci-json__toggle pvci-json__toggle--leaf";
        toggle.textContent = container ? (isCollapsed ? "▶" : "▼") : "·";
        if (container) {
            toggle.addEventListener("click", () => {
                if (this.collapsed.has(node.path)) this.collapsed.delete(node.path);
                else this.collapsed.add(node.path);
                this.render();
            });
        }
        row.appendChild(toggle);

        if (node.key !== null) {
            const k = document.createElement("span");
            k.className = "pvci-json__key";
            k.textContent = JSON.stringify(node.key);
            row.appendChild(k);
            row.appendChild(punct(": "));
        }

        let selfMatches = false;
        if (this.filter) {
            const hay = `${node.key ?? ""} ${container ? "" : String(node.value)}`.toLowerCase();
            selfMatches = hay.includes(this.filter);
        }

        if (container) {
            const entries = entriesOf(node.value);
            const open = Array.isArray(node.value) ? "[" : "{";
            const close = Array.isArray(node.value) ? "]" : "}";
            row.appendChild(punct(open));

            if (isCollapsed || entries.length === 0) {
                if (entries.length) {
                    const meta = document.createElement("span");
                    meta.className = "pvci-json__meta";
                    meta.textContent = ` ${entries.length} `;
                    row.appendChild(meta);
                }
                row.appendChild(punct(close));
            }

            const holder = document.createElement("div");
            let childMatched = false;
            if (!isCollapsed && entries.length) {
                entries.forEach(([k, v]) => {
                    const shown = this.renderNode(
                        { path: `${node.path}/${k}`, key: k, value: v, depth: node.depth + 1 },
                        holder,
                        counts
                    );
                    childMatched = childMatched || shown;
                });
            }

            const keep = !this.filter || selfMatches || childMatched;
            if (keep) {
                if (selfMatches) {
                    row.classList.add("pvci-json__row--hit");
                    counts.shown++;
                }
                host.appendChild(row);
                if (!isCollapsed && entries.length) {
                    host.appendChild(holder);
                    const closeRow = document.createElement("div");
                    closeRow.className = "pvci-json__row";
                    closeRow.style.paddingLeft = `${node.depth * 14 + 13}px`;
                    closeRow.appendChild(punct(close));
                    host.appendChild(closeRow);
                }
            }
            return keep;
        }

        row.appendChild(scalar(node.value));
        const keep = !this.filter || selfMatches;
        if (keep) {
            if (selfMatches) {
                row.classList.add("pvci-json__row--hit");
                counts.shown++;
            }
            host.appendChild(row);
        }
        return keep;
    }

    public getOutputs(): IOutputs {
        return {};
    }

    public destroy(): void {
        this.root?.remove();
    }
}

function isContainer(v: Json): v is Json[] | Record<string, Json> {
    return v !== null && typeof v === "object";
}

function entriesOf(v: Json): [string, Json][] {
    if (Array.isArray(v)) return v.map((item, i) => [String(i), item] as [string, Json]);
    if (v !== null && typeof v === "object") return Object.entries(v);
    return [];
}

function punct(text: string): HTMLSpanElement {
    const s = document.createElement("span");
    s.className = "pvci-json__punct";
    s.textContent = text;
    return s;
}

function scalar(v: Json): HTMLSpanElement {
    const s = document.createElement("span");
    if (v === null) {
        s.className = "pvci-json__null";
        s.textContent = "null";
    } else if (typeof v === "boolean") {
        s.className = "pvci-json__bool";
        s.textContent = String(v);
    } else if (typeof v === "number") {
        s.className = "pvci-json__num";
        s.textContent = String(v);
    } else {
        s.className = "pvci-json__str";
        const text = String(v);
        s.textContent =
            text.length > MAX_INLINE_STRING
                ? `${JSON.stringify(text.slice(0, MAX_INLINE_STRING))} … (${text.length.toLocaleString()} chars)`
                : JSON.stringify(text);
        if (text.length > MAX_INLINE_STRING) s.title = text.slice(0, 4000);
    }
    return s;
}
