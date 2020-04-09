
import Jupyter from 'base/js/namespace'
import React from 'react'
import axios from 'axios'
import _ from 'lodash'

import {EditorView, PluginValue, Decoration, ViewUpdate, ViewPlugin} from "@codemirror/next/view"
import {foldGutter, foldCode, unfoldCode} from "@codemirror/next/fold"
import {EditorState, Syntax, Extension, StateField} from "@codemirror/next/state"
import {lineNumbers} from "@codemirror/next/gutter"
import {Tree, NodeType, NodeGroup} from 'lezer-tree'
import {history, redo, redoSelection, undo, undoSelection} from "@codemirror/next/history"
import {keymap} from "@codemirror/next/keymap"
import {baseKeymap, indentSelection} from "@codemirror/next/commands"
import {defaultHighlighter} from "@codemirror/next/highlight"
import {styleTags} from "@codemirror/next/highlight"
import {RangeSetBuilder, RangeSet} from "@codemirror/next/rangeset"



declare var __non_webpack_require__: any;
declare global { interface Window { Module: any; PythonParser: any } }

async function parser_init(): Promise<any> {
  const BASE_URL = '/nbextensions/inliner_jupyter/dist';
  const response = await axios.get(`${BASE_URL}/tree-sitter.wasm`, {responseType: 'arraybuffer'});
  const buffer = response.data;
  if (window.PythonParser) {
      return window.PythonParser;
  }

  window.Module = {wasmBinary: buffer};
  return new Promise(function(success, fail) {
    __non_webpack_require__([`${BASE_URL}/tree-sitter.js`], function(Parser: any) {
      async function inner() {
        await Parser.init();
        const PythonLang = await Parser.Language.load(`${BASE_URL}/tree-sitter-python.wasm`);
        let parser = new Parser();
        parser.setLanguage(PythonLang);
        window.PythonParser = parser;
        success(parser);
      }
      inner();
    });
  });
}


class SitterTree {
  tree: Parser.Tree
  node_types: {[key: string]: NodeType}
  
  constructor(tree: Parser.Tree) {
    this.tree = tree;
    this.node_types = {};
  }

  private node_group(): NodeGroup {
    const group = new NodeGroup(Object.values(this.node_types).sort((a, b) => a.id - b.id));
    return group.extend(styleTags({
      '" string': "string",
      "identifier": "variableName",
      "assignment": "definition",
      "true false": "atom",
      "integer": "number",
      "if else for": "keyword control"
    }));
  }

  private build_node(node: Parser.SyntaxNode): number[] {
    const buffer = _.flatten(node.children.map((child) => this.build_node(child)));
    if (!this.node_types.hasOwnProperty(node.type)) {
      this.node_types[node.type] = new NodeType(node.type, {}, Object.keys(this.node_types).length);
    }
    const node_type = this.node_types[node.type];
    return buffer.concat([node_type.id, node.startIndex, node.endIndex, buffer.length + 4]);
  }

  build(): Tree {
    const buffer = this.build_node(this.tree.rootNode);
    const group = this.node_group();
    return Tree.build({buffer, group});
  }
}

class PythonSyntax implements Syntax {
  readonly extension: Extension
  readonly field: StateField<Parser.Tree>

  constructor(parser: Parser) {
    const that = this;
    this.field = StateField.define<Parser.Tree>({
      create(state) { return parser.parse(state.doc.toString()); },
      update(value, tr) { return value; }
    });
    this.extension = [this.field, EditorState.syntax.of(this)];
  }

  getTree(state: EditorState): Tree {
    const tree = state.field(this.field);
    const sitter_tree = new SitterTree(tree);
    return  sitter_tree.build();
  }

  parsePos(state: EditorState): number {
    return state.doc.length;
  }

  ensureTree(state: EditorState, upto: number, timeout?: number): null | Tree {
    return this.getTree(state);
  }

  get docNodeType(): NodeType { throw Error("NYI"); }
  
  docNodeTypeAt(state: EditorState, pos: number): NodeType {
    throw Error("NYI");
  }
}

class DeadCode implements PluginValue {
    decorations: RangeSet<Decoration>

    constructor(dead_code: number[][]) {
        let builder = new RangeSetBuilder<Decoration>();
        dead_code.sort((a, b) => a[0] - b[0]).forEach(([start, end]) => {
            builder.add(start, end, Decoration.mark({class: 'deadcode'}));
        });
        this.decorations = builder.finish();
    }

    update(update: ViewUpdate) {
        // pass
    }    
}

type CodeEditorProps = {
    code: string,  
    dead_code: number[][]
}

export class CodeEditor extends React.Component<CodeEditorProps> {
  editor: EditorView | null = null
  node: Element | null = null

  notebook_defocus_plugin() {
    return EditorView.domEventHandlers({
      focus: () => { Jupyter.keyboard_manager.disable(); return true; },
      blur: () => { Jupyter.keyboard_manager.enable(); return true; }
    });
  }

  async componentDidMount() {
    const parser = await parser_init();
    const python_syntax = new PythonSyntax(parser);
    const extensions: any[] = [
      this.notebook_defocus_plugin(),
      foldGutter({}),
      lineNumbers(),
      history(),
      keymap({
        "Mod-z": undo,
        "Mod-Shift-z": redo,
        "Mod-u": view => undoSelection(view) || true,
        "Mod-Shift-u": redoSelection,
        "Shift-Tab": indentSelection,
        "Mod-Alt-[": foldCode,
        "Mod-Alt-]": unfoldCode,
      }),
      keymap(baseKeymap),
      python_syntax.extension,
      defaultHighlighter,
      ViewPlugin.define(_ => new DeadCode(this.props.dead_code)).decorations(),
    ]

    const doc = this.props.code;
    const state = EditorState.create({doc, extensions});
    this.editor = new EditorView({state});
    this.node!.appendChild(this.editor.dom);
  }

  render() {
    return <div ref={(node) => { 
      if (node instanceof Element) {
        this.node = node; 
      }
    }} />;
  }
}
