export abstract class Env {
  format_trace(traceback: string[]): string {
    let trace = traceback.join('\n');
    // https://stackoverflow.com/questions/25245716/remove-all-ansi-colors-styles-from-strings/29497680
    let trace_no_color = trace.replace(
      /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
    return trace_no_color;
  }

  abstract execute(pysrc: string, wait_for_output: boolean): Promise<string | null>;

  abstract show_error(error: string): void;

  abstract get_and_insert(): {text: string, cell_id: string, methods: any};
  
  abstract get_selected_text(): string;

  abstract get_cursor_pos(): {line: number, column: number} | null;

  abstract create_new_cell(text: string): void;  
};

let ENV: Env;
export let get_env = () => ENV;
export let set_env = (env: Env) => { ENV = env; }
