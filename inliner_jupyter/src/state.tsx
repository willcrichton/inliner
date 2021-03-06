import _ from 'lodash';

import {
  observable,
  computed,
  autorun,
  ObservableMap,
  IObservableArray
} from 'mobx';

import {
  get_env
} from './env';

export let check_call = async (pysrc: string) : Promise<void> => { 
  let _ = await get_env().execute(pysrc, false);  
};
export let check_output = async (pysrc: string) : Promise<string> => { 
  let outp = await get_env().execute(pysrc, true); 
  return outp!; 
}

class PythonBridge {
  name: string

  constructor(name: string) {
    this.name = name;
  }

  async setup(contents: any) {
    let src = `
from inliner import InteractiveInliner
from inliner.targets import CursorTarget
import json
${this.name} = InteractiveInliner(${JSON.stringify(contents)}, globls=globals())`;
    return check_call(src);
  }

  async make_program() {
    var print = `print(${this.name}.code())`;
    let output = await check_output(print);
    return output.trim();
  }

  async target_suggestions() {
    let refresh = `
print(json.dumps(${this.name}.target_suggestions()))`;
    let outp = await check_output(refresh);
    return JSON.parse(outp);
  }

  async code_folding() {
    const outp = await check_output(`
print(json.dumps(${this.name}.code_folding()))`);
    return JSON.parse(outp);
  }

  async undo() {
    return check_call(`${this.name}.undo()`);
  }

  async run_pass(pass: string, fixpoint = false) {
    const inner_call = `${this.name}.run_pass("${pass}")`;
    let call = fixpoint ? `${this.name}.fixpoint(lambda: ${inner_call})` : inner_call;
    let outp = await check_output(`print(${call})`);
    outp = outp.trim();

    // If running pass generates some output, we only want to look at
    // the end of stdout
    let lines = outp.split('\n');
    let last_line = lines[lines.length - 1];

    if (last_line != 'True' && last_line != 'False') {
      throw `${pass}: ${outp}`;
    }

    return outp == 'True';
  }

  async add_target(target: string) {
    return check_call(`${this.name}.add_target(${target})`);
  }

  async sync_targets(targets: any[]) {
    let names = targets.map((t) => t.name);
    var save = `
for target in ${this.name}.targets:
  ${this.name}.remove_target(target)
for target in json.loads('${JSON.stringify(names)}'):
    ${this.name}.add_target(target)`;

    return check_call(save);
  }

  async last_pass() {
    try {
      const ret = await check_output(`print(${this.name}.history[-1][1])`);
      return ret;
    } catch (error) {
      return null;
    }
  }

  async debug() {
    return check_output(`print(${this.name}.debug())`);
  }

  async get_object_path(src: string) {
    const out = await check_output(`
tracer = ${this.name}.execute();
exec("""
from inliner.visitors import object_path
print(object_path(${src}))
    """, tracer.globls)`);
    return out.trim();
  }
}

let spinner = (target: any, name: string, descriptor: any) => {
  const original = descriptor.value;
  descriptor.value = async function(...args: any[]) {
    let toggled = !this.notebook_state.show_spinner;
    if (toggled) {
      this.notebook_state.show_spinner = true;
    }

    try {
      let ret = await original.apply(this, args);
      return ret;
    } finally {
      if (toggled) {
        this.notebook_state.show_spinner = false;
      }
    }
  }
}

export type Target = {name: string, path: string, use: string};

export class InlineState {
  @observable cell_id: string
  @observable targets: IObservableArray<Target>
  @observable.shallow target_suggestions: ObservableMap<string, any> 
  @observable program_history: any[]

  bridge: PythonBridge
  notebook_state: NotebookState
  methods: any

  constructor(methods: any, notebook_state: NotebookState) {
    this.cell_id = notebook_state.current_cell!;
    this.targets = observable.array();
    this.target_suggestions = new ObservableMap();
    this.program_history = [];

    this.methods = methods;
    this.bridge = new PythonBridge('inliner');
    this.notebook_state = notebook_state;
  }

  @spinner
  async setup(contents: string) {
    await this.bridge.setup(contents);
    await this.update_cell();

    autorun(() => {
      this.bridge.sync_targets(this.targets);
    });
  }

  @spinner
  async update_cell() {
    let src = await this.bridge.make_program();
    this.methods.set_cell_text(src);
    this.program_history.push(src);
  }

  @spinner
  async refresh_target_suggestions() {
    let suggestions = await this.bridge.target_suggestions();
    suggestions = _.pickBy(suggestions, (v: any, k: string) =>
      this.targets.filter((t) => t.name == k).length == 0);
    this.target_suggestions.clear();
    this.target_suggestions.merge(suggestions);
  }

  @spinner
  async undo() {
    await this.bridge.undo();
    await this.update_cell();
    this.program_history.pop();
    this.program_history.pop();
  }

  @spinner
  async run_pass(pass: string, fixpoint = false) {
    let ret = await this.bridge.run_pass(pass, fixpoint);
    await this.update_cell();
    return ret;
  }

  async last_pass() {
    return this.bridge.last_pass();
  }

  debug() {
    return this.bridge.debug();
  }

  get_object_path(src: string) {
    return this.bridge.get_object_path(src);
  }

  async fold_code() {
    let fold_lines = await this.bridge.code_folding();
    this.methods.fold_lines(fold_lines);
  }

  @spinner
  async inline(cursor: {line: number, column: number}) {
    await this.bridge.add_target(`CursorTarget((${cursor.line}, ${cursor.column}))`);
    await this.run_pass('inline');
  }

  @spinner
  async optimize() {
    let run_until = async (passes: string[]) => {
      while (true) {
        var any_pass = false;
        for (var pass of passes) {
          console.log(`Running ${pass}`);
          var change = await this.run_pass(pass, pass == 'deadcode');
          any_pass = any_pass || change;
          console.log(`Finished ${pass}, change: ${change}`);
        }

        if (!any_pass) {
          return;
        }
      }
    };

    let passes = [
      'inline',
      'dead_code',
      'copy_propagation',
      'unused_vars',
      'clean_imports',
    ];

    await run_until(passes);
    await this.run_pass('record_to_vars');
    await run_until(passes);

    await this.run_pass('remove_suffixes');
    await this.fold_code();

    await this.refresh_target_suggestions();
  }
}

export class NotebookState {
  @observable states: {[key: string]: InlineState} = {}
  @observable current_cell: string | null = null
  @observable show_spinner = false

  add_state(state: InlineState) {
    this.states[state.cell_id] = state;
  }

  @computed get current_state() {
    return this.states[this.current_cell!];
  }
}
