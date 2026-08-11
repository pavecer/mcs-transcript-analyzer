/*
 * ATTENTION: The "eval" devtool has been used (maybe by default in mode: "development").
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
var pcf_tools_652ac3f36e1e4bca82eb3c1dc44e6fad;
/******/ (() => { // webpackBootstrap
/******/ 	"use strict";
/******/ 	var __webpack_modules__ = ({

/***/ "./JsonViewer/index.ts"
/*!*****************************!*\
  !*** ./JsonViewer/index.ts ***!
  \*****************************/
(__unused_webpack_module, __webpack_exports__, __webpack_require__) {

eval("{__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   JsonViewer: () => (/* binding */ JsonViewer)\n/* harmony export */ });\nfunction _slicedToArray(r, e) { return _arrayWithHoles(r) || _iterableToArrayLimit(r, e) || _unsupportedIterableToArray(r, e) || _nonIterableRest(); }\nfunction _nonIterableRest() { throw new TypeError(\"Invalid attempt to destructure non-iterable instance.\\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.\"); }\nfunction _unsupportedIterableToArray(r, a) { if (r) { if (\"string\" == typeof r) return _arrayLikeToArray(r, a); var t = {}.toString.call(r).slice(8, -1); return \"Object\" === t && r.constructor && (t = r.constructor.name), \"Map\" === t || \"Set\" === t ? Array.from(r) : \"Arguments\" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0; } }\nfunction _arrayLikeToArray(r, a) { (null == a || a > r.length) && (a = r.length); for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e]; return n; }\nfunction _iterableToArrayLimit(r, l) { var t = null == r ? null : \"undefined\" != typeof Symbol && r[Symbol.iterator] || r[\"@@iterator\"]; if (null != t) { var e, n, i, u, a = [], f = !0, o = !1; try { if (i = (t = t.call(r)).next, 0 === l) { if (Object(t) !== t) return; f = !1; } else for (; !(f = (e = i.call(t)).done) && (a.push(e.value), a.length !== l); f = !0); } catch (r) { o = !0, n = r; } finally { try { if (!f && null != t.return && (u = t.return(), Object(u) !== u)) return; } finally { if (o) throw n; } } return a; } }\nfunction _arrayWithHoles(r) { if (Array.isArray(r)) return r; }\nvar MAX_INLINE_STRING = 400;\nclass JsonViewer {\n  constructor() {\n    this.parsed = null;\n    this.parseError = null;\n    this.rawText = \"\";\n    this.collapsed = new Set();\n    this.filter = \"\";\n    this.rawMode = false;\n    this.autoDepth = 2;\n  }\n  init(context, _notifyOutputChanged, _state, container) {\n    var _a, _b, _c;\n    this.autoDepth = (_b = (_a = context.parameters.startCollapsedDepth) === null || _a === void 0 ? void 0 : _a.raw) !== null && _b !== void 0 ? _b : 2;\n    this.root = document.createElement(\"div\");\n    this.root.className = \"pvci-json\";\n    this.root.style.height = \"\".concat(((_c = context.parameters.viewerHeight) === null || _c === void 0 ? void 0 : _c.raw) || 460, \"px\");\n    var bar = document.createElement(\"div\");\n    bar.className = \"pvci-json__bar\";\n    var mkBtn = (text, title, onClick) => {\n      var b = document.createElement(\"button\");\n      b.type = \"button\";\n      b.textContent = text;\n      b.title = title;\n      b.addEventListener(\"click\", onClick);\n      bar.appendChild(b);\n      return b;\n    };\n    mkBtn(\"Expand all\", \"Expand every node\", () => {\n      this.collapsed.clear();\n      this.render();\n    });\n    mkBtn(\"Collapse all\", \"Collapse every node\", () => {\n      this.collapseAll(0);\n      this.render();\n    });\n    this.rawBtn = mkBtn(\"Raw\", \"Toggle raw text\", () => {\n      this.rawMode = !this.rawMode;\n      this.rawBtn.setAttribute(\"aria-pressed\", String(this.rawMode));\n      this.render();\n    });\n    this.rawBtn.setAttribute(\"aria-pressed\", \"false\");\n    mkBtn(\"Copy\", \"Copy JSON to clipboard\", () => {\n      var _a;\n      void ((_a = navigator.clipboard) === null || _a === void 0 ? void 0 : _a.writeText(this.rawText));\n    });\n    this.searchBox = document.createElement(\"input\");\n    this.searchBox.className = \"pvci-json__search\";\n    this.searchBox.type = \"search\";\n    this.searchBox.placeholder = \"Filter keys and values…\";\n    this.searchBox.addEventListener(\"input\", () => {\n      this.filter = this.searchBox.value.trim().toLowerCase();\n      this.render();\n    });\n    bar.appendChild(this.searchBox);\n    this.stat = document.createElement(\"span\");\n    this.stat.className = \"pvci-json__stat\";\n    bar.appendChild(this.stat);\n    this.body = document.createElement(\"div\");\n    this.body.className = \"pvci-json__body\";\n    this.root.appendChild(bar);\n    this.root.appendChild(this.body);\n    container.appendChild(this.root);\n  }\n  updateView(context) {\n    var _a, _b, _c;\n    var next = (_b = (_a = context.parameters.jsonValue) === null || _a === void 0 ? void 0 : _a.raw) !== null && _b !== void 0 ? _b : \"\";\n    if (next !== this.rawText) {\n      this.rawText = next;\n      this.parse();\n      this.collapseAll(this.autoDepth);\n    }\n    this.root.style.height = \"\".concat(((_c = context.parameters.viewerHeight) === null || _c === void 0 ? void 0 : _c.raw) || 460, \"px\");\n    this.render();\n  }\n  parse() {\n    this.parseError = null;\n    this.parsed = null;\n    var text = this.rawText.trim();\n    if (!text) return;\n    try {\n      this.parsed = JSON.parse(text);\n    } catch (e) {\n      this.parseError = e instanceof Error ? e.message : String(e);\n    }\n  }\n  /** Collapse containers at or below `depth` so large payloads open instantly. */\n  collapseAll(depth) {\n    this.collapsed.clear();\n    var walk = (value, path, d) => {\n      if (!isContainer(value)) return;\n      if (d >= depth) this.collapsed.add(path);\n      entriesOf(value).forEach(_ref => {\n        var _ref2 = _slicedToArray(_ref, 2),\n          k = _ref2[0],\n          v = _ref2[1];\n        return walk(v, \"\".concat(path, \"/\").concat(k), d + 1);\n      });\n    };\n    walk(this.parsed, \"$\", 0);\n  }\n  render() {\n    this.body.textContent = \"\";\n    if (this.parseError) {\n      var d = document.createElement(\"div\");\n      d.className = \"pvci-json__error\";\n      d.textContent = \"Not valid JSON \\u2014 showing raw text.\\n\".concat(this.parseError);\n      this.body.appendChild(d);\n      this.appendRaw();\n      this.stat.textContent = \"\".concat(this.rawText.length.toLocaleString(), \" chars\");\n      return;\n    }\n    if (!this.rawText.trim()) {\n      var _d = document.createElement(\"div\");\n      _d.className = \"pvci-json__empty\";\n      _d.textContent = \"No content.\";\n      this.body.appendChild(_d);\n      this.stat.textContent = \"\";\n      return;\n    }\n    if (this.rawMode) {\n      this.appendRaw();\n      this.stat.textContent = \"\".concat(this.rawText.length.toLocaleString(), \" chars\");\n      return;\n    }\n    var counts = {\n      nodes: 0,\n      shown: 0\n    };\n    this.renderNode({\n      path: \"$\",\n      key: null,\n      value: this.parsed,\n      depth: 0\n    }, this.body, counts);\n    var size = \"\".concat(this.rawText.length.toLocaleString(), \" chars\");\n    this.stat.textContent = this.filter ? \"\".concat(counts.shown.toLocaleString(), \" match / \").concat(counts.nodes.toLocaleString(), \" nodes \\xB7 \").concat(size) : \"\".concat(counts.nodes.toLocaleString(), \" nodes \\xB7 \").concat(size);\n  }\n  appendRaw() {\n    var pre = document.createElement(\"pre\");\n    pre.className = \"pvci-json__raw\";\n    pre.textContent = this.rawText;\n    this.body.appendChild(pre);\n  }\n  renderNode(node, host, counts) {\n    var _a;\n    counts.nodes++;\n    var container = isContainer(node.value);\n    var isCollapsed = container && this.collapsed.has(node.path);\n    var row = document.createElement(\"div\");\n    row.className = \"pvci-json__row\";\n    row.style.paddingLeft = \"\".concat(node.depth * 14, \"px\");\n    var toggle = document.createElement(\"span\");\n    toggle.className = container ? \"pvci-json__toggle\" : \"pvci-json__toggle pvci-json__toggle--leaf\";\n    toggle.textContent = container ? isCollapsed ? \"▶\" : \"▼\" : \"·\";\n    if (container) {\n      toggle.addEventListener(\"click\", () => {\n        if (this.collapsed.has(node.path)) this.collapsed.delete(node.path);else this.collapsed.add(node.path);\n        this.render();\n      });\n    }\n    row.appendChild(toggle);\n    if (node.key !== null) {\n      var k = document.createElement(\"span\");\n      k.className = \"pvci-json__key\";\n      k.textContent = JSON.stringify(node.key);\n      row.appendChild(k);\n      row.appendChild(punct(\": \"));\n    }\n    var selfMatches = false;\n    if (this.filter) {\n      var hay = \"\".concat((_a = node.key) !== null && _a !== void 0 ? _a : \"\", \" \").concat(container ? \"\" : String(node.value)).toLowerCase();\n      selfMatches = hay.includes(this.filter);\n    }\n    if (container) {\n      var entries = entriesOf(node.value);\n      var open = Array.isArray(node.value) ? \"[\" : \"{\";\n      var close = Array.isArray(node.value) ? \"]\" : \"}\";\n      row.appendChild(punct(open));\n      if (isCollapsed || entries.length === 0) {\n        if (entries.length) {\n          var meta = document.createElement(\"span\");\n          meta.className = \"pvci-json__meta\";\n          meta.textContent = \" \".concat(entries.length, \" \");\n          row.appendChild(meta);\n        }\n        row.appendChild(punct(close));\n      }\n      var holder = document.createElement(\"div\");\n      var childMatched = false;\n      if (!isCollapsed && entries.length) {\n        entries.forEach(_ref3 => {\n          var _ref4 = _slicedToArray(_ref3, 2),\n            k = _ref4[0],\n            v = _ref4[1];\n          var shown = this.renderNode({\n            path: \"\".concat(node.path, \"/\").concat(k),\n            key: k,\n            value: v,\n            depth: node.depth + 1\n          }, holder, counts);\n          childMatched = childMatched || shown;\n        });\n      }\n      var _keep = !this.filter || selfMatches || childMatched;\n      if (_keep) {\n        if (selfMatches) {\n          row.classList.add(\"pvci-json__row--hit\");\n          counts.shown++;\n        }\n        host.appendChild(row);\n        if (!isCollapsed && entries.length) {\n          host.appendChild(holder);\n          var closeRow = document.createElement(\"div\");\n          closeRow.className = \"pvci-json__row\";\n          closeRow.style.paddingLeft = \"\".concat(node.depth * 14 + 13, \"px\");\n          closeRow.appendChild(punct(close));\n          host.appendChild(closeRow);\n        }\n      }\n      return _keep;\n    }\n    row.appendChild(scalar(node.value));\n    var keep = !this.filter || selfMatches;\n    if (keep) {\n      if (selfMatches) {\n        row.classList.add(\"pvci-json__row--hit\");\n        counts.shown++;\n      }\n      host.appendChild(row);\n    }\n    return keep;\n  }\n  getOutputs() {\n    return {};\n  }\n  destroy() {\n    var _a;\n    (_a = this.root) === null || _a === void 0 ? void 0 : _a.remove();\n  }\n}\nfunction isContainer(v) {\n  return v !== null && typeof v === \"object\";\n}\nfunction entriesOf(v) {\n  if (Array.isArray(v)) return v.map((item, i) => [String(i), item]);\n  if (v !== null && typeof v === \"object\") return Object.entries(v);\n  return [];\n}\nfunction punct(text) {\n  var s = document.createElement(\"span\");\n  s.className = \"pvci-json__punct\";\n  s.textContent = text;\n  return s;\n}\nfunction scalar(v) {\n  var s = document.createElement(\"span\");\n  if (v === null) {\n    s.className = \"pvci-json__null\";\n    s.textContent = \"null\";\n  } else if (typeof v === \"boolean\") {\n    s.className = \"pvci-json__bool\";\n    s.textContent = String(v);\n  } else if (typeof v === \"number\") {\n    s.className = \"pvci-json__num\";\n    s.textContent = String(v);\n  } else {\n    s.className = \"pvci-json__str\";\n    var text = String(v);\n    s.textContent = text.length > MAX_INLINE_STRING ? \"\".concat(JSON.stringify(text.slice(0, MAX_INLINE_STRING)), \" \\u2026 (\").concat(text.length.toLocaleString(), \" chars)\") : JSON.stringify(text);\n    if (text.length > MAX_INLINE_STRING) s.title = text.slice(0, 4000);\n  }\n  return s;\n}\n\n//# sourceURL=webpack://pcf_tools_652ac3f36e1e4bca82eb3c1dc44e6fad/./JsonViewer/index.ts?\n}");

/***/ }

/******/ 	});
/************************************************************************/
/******/ 	// The require scope
/******/ 	const __webpack_require__ = {};
/******/
/************************************************************************/
/******/ 	/* webpack/runtime/define property getters */
/******/ 	(() => {
/******/ 		// define getter/value functions for harmony exports
/******/ 		__webpack_require__.d = (exports, definition) => {
/******/ 			if(Array.isArray(definition)) {
/******/ 				var i = 0;
/******/ 				while(i < definition.length) {
/******/ 					var key = definition[i++];
/******/ 					var binding = definition[i++];
/******/ 					if(!__webpack_require__.o(exports, key)) {
/******/ 						if(binding === 0) {
/******/ 							Object.defineProperty(exports, key, { enumerable: true, value: definition[i++] });
/******/ 						} else {
/******/ 							Object.defineProperty(exports, key, { enumerable: true, get: binding });
/******/ 						}
/******/ 					} else if(binding === 0) { i++; }
/******/ 				}
/******/ 			} else {
/******/ 				for(var key in definition) {
/******/ 					if(__webpack_require__.o(definition, key) && !__webpack_require__.o(exports, key)) {
/******/ 						Object.defineProperty(exports, key, { enumerable: true, get: definition[key] });
/******/ 					}
/******/ 				}
/******/ 			}
/******/ 		};
/******/ 	})();
/******/
/******/ 	/* webpack/runtime/hasOwnProperty shorthand */
/******/ 	(() => {
/******/ 		__webpack_require__.o = (obj, prop) => (Object.prototype.hasOwnProperty.call(obj, prop))
/******/ 	})();
/******/
/******/ 	/* webpack/runtime/make namespace object */
/******/ 	(() => {
/******/ 		// define __esModule on exports
/******/ 		__webpack_require__.r = (exports) => {
/******/ 			if(Symbol.toStringTag) {
/******/ 				Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
/******/ 			}
/******/ 			Object.defineProperty(exports, '__esModule', { value: true });
/******/ 		};
/******/ 	})();
/******/
/************************************************************************/
/******/
/******/ 	// startup
/******/ 	// Load entry module and return exports
/******/ 	// This entry module can't be inlined because the eval devtool is used.
/******/ 	let __webpack_exports__ = {};
/******/ 	__webpack_modules__["./JsonViewer/index.ts"](0,__webpack_exports__,__webpack_require__);
/******/ 	pcf_tools_652ac3f36e1e4bca82eb3c1dc44e6fad = __webpack_exports__;
/******/
/******/ })()
;
if (window.ComponentFramework && window.ComponentFramework.registerControl) {
	ComponentFramework.registerControl('PvciControls.JsonViewer', pcf_tools_652ac3f36e1e4bca82eb3c1dc44e6fad.JsonViewer);
} else {
	var PvciControls = PvciControls || {};
	PvciControls.JsonViewer = pcf_tools_652ac3f36e1e4bca82eb3c1dc44e6fad.JsonViewer;
	pcf_tools_652ac3f36e1e4bca82eb3c1dc44e6fad = undefined;
}