import Jupyter from 'base/js/namespace';

let format_trace = (reply) => {
  var trace = reply.content.traceback.join('\n');
  // https://stackoverflow.com/questions/25245716/remove-all-ansi-colors-styles-from-strings/29497680
  var trace_no_color = trace.replace(
    /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
  return trace_no_color;
};

let call = (pysrc, wait_output) => {
  pysrc = pysrc.trim();
  return new Promise((resolve, reject) => {
    Jupyter.notebook.kernel.execute(pysrc, {
      shell: {
        reply: (reply) => {
          if (!wait_output) {
            if (reply.content.status == 'error') {
              reject(format_trace(reply));
            } else {
              resolve(reply);
            }
          }
        },
      },
      iopub: {
        output: (reply) => {
          if (wait_output) {
            if (reply.msg_type == 'error') {
              reject(format_trace(reply));
            } else {
              // HACK: if a call both prints to stdout and raises
              // an exception, then the iopub.output callback receives
              // two messages, and the stdout comes before the error.
              // We can wait a little bit to see if we get the error first
              // before resolving.
              setTimeout(() => {
                resolve(reply.content.text)
              }, 100);
            }
          }
        }
      }
    });
  });
}


export let check_call = (pysrc) => call(pysrc, false);
export let check_output = (pysrc) => call(pysrc, true);
