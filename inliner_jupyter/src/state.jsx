import _ from 'lodash';

import {
  observable,
  computed,
  autorun
} from 'mobx';

import {
  get_env
} from './env';

export let check_call = (pysrc) => get_env().execute(pysrc, false);
export let check_output = (pysrc) => get_env().execute(pysrc, true);

class PythonBridge {
  constructor(name) {
    this.name = name;
  }

  async setup(contents) {
    let src = `
from inliner import InteractiveInliner
import json
${this.name} = InteractiveInliner(${JSON.stringify(contents)}, globls=globals())`;
    return check_call(src);
  }

  async make_program() {
    var print = `print(${this.name}.code())`;
    let output = await check_output(print);
    return output.trimEnd();
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

  async run_pass(pass, fixpoint = false) {
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

  async sync_targets(targets) {
    let names = targets.map((t) => t.name);
    var save = `
${this.name}.targets = []
for target in json.loads('${JSON.stringify(names)}'):
    ${this.name}.add_target(target)`;

    return check_call(save);
  }

  async last_pass() {
    return check_output(`print(${this.name}.history[-1][1])`);
  }

  async debug() {
    return check_output(`print(${this.name}.debug())`);
  }

  async get_object_path(src) {
    const out = await check_output(`
tracer = ${this.name}.execute();
exec("""
from inliner.visitors import object_path
print(object_path(${src}))
    """, tracer.globls)`);
    return out.trim();
  }
}

let spinner = (target, name, descriptor) => {
  const original = descriptor.value;
  descriptor.value = async function(...args) {
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

export class InlineState {
  @observable cell_id
  @observable targets = []
  @observable.shallow target_suggestions = new Map();
  @observable program_history = []

  constructor(methods, notebook_state) {
    this.cell_id = notebook_state.current_cell;
    this.methods = methods;
    this.bridge = new PythonBridge('inliner');
    this.notebook_state = notebook_state;
  }

  @spinner
  async setup(contents) {
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
    suggestions = _.pickBy(suggestions, (v, k) =>
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
  async run_pass(pass, fixpoint = false) {
    if (pass == 'inline' && this.targets.length == 0) {
      throw "Must have at least one inline target to run inline pass";
    }

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

  get_object_path(src) {
    return this.bridge.get_object_path(src);
  }

  async fold_code() {
    let fold_lines = await this.bridge.code_folding();
    this.methods.fold_lines(fold_lines);
  }

  @spinner
  async optimize() {
    let run_until = async (passes) => {
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
      'clean_imports'
    ];

    await run_until(passes);
    await this.run_pass('record_to_vars');
    await run_until(passes);

    //await this.run_pass('remove_suffixes');
    await this.fold_code();

    await this.refresh_target_suggestions();
  }
}

export class NotebookState {
  @observable states = {}
  @observable current_cell = null
  @observable show_spinner = false

  add_state(state) {
    this.states[state.cell_id] = state;
  }

  @computed get current_state() {
    return this.states[this.current_cell];
  }
}
