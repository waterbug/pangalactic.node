from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
import json, sys
# import subprocess
from subprocess import PIPE, Popen
from threading  import Thread
# install_aliases() makes 'queue' python2-compatible
from queue import Queue, Empty

ON_POSIX = 'posix' in sys.builtin_module_names

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

def run_conda(*args, **kwargs):
    """
    Run conda in nonblocking mode and emit progress signals.

    Args:
        args (tuple):  conda arguments, excluding 'conda', which should
            include '--json' if progress signal is to be emitted.  E.g.:

            ['install', '--json', '-y', pkg_name]

    Keyword Args:
        progress_signal (pyqtSignal):  signal object (passed in by Worker when
            it calls this function)
    """
    conda_cmd = ['conda'] + list(args)
    progress_signal = kwargs.get('progress_signal')
    if sys.platform == 'win32':
        # import win32api
        # use `startupinfo` to prevent opening a Windows console ...???
        # si = subprocess.STARTUPINFO()
        # si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                  # startupinfo=si)
        # DETACHED_PROCESS = 0x00000008  # DID NOT WORK
        CREATE_NO_WINDOW = 0x08000000
        p = Popen(conda_cmd, stdout=PIPE, stderr=PIPE, bufsize=1,
                  close_fds=ON_POSIX, universal_newlines=True,
                  creationflags=CREATE_NO_WINDOW)
    else:
        p = Popen(conda_cmd, stdout=PIPE, stderr=PIPE, bufsize=1,
                  close_fds=ON_POSIX)
    # output_pipe = p.communicate()[0]  # DID NOT WORK
    q = Queue()
    t = Thread(target=enqueue_output, args=(p.stdout, q))
    # Force the thread to die when the process ends
    t.daemon = True
    t.start()
    buf = ''
    output_started = False
    # waiting = False
    status = False
    pkgs = []
    result = []
    while 1:
        try:
            # line = q.get()
            line = q.get(timeout=10)
        except Empty:
            if output_started:
                # try:
                d = json.loads(buf)
                if type(d) is dict:
                    actions = d.get('actions')
                    if actions and actions.get('LINK'):
                        pkgs = ['-'.join([pkg['name'], pkg['version']])
                                for pkg in actions['LINK']]
                    # status = d.get('success')
                else:   # 'conda list'
                    pkgs = ['-'.join([pkg['name'], pkg['version']])
                            for pkg in d]
                status = True
                result = status, pkgs
                # DEBUG prints
                # print(buf + '\n')
                # print(' - end of stuff -')
                break
            # else:
                # DEBUG prints
                # if waiting:
                    # # print('.', end='')
                    # sys.stdout.flush()
                # else:
                    # # print('connecting ...', end='')
                    # waiting = True
        else:  # got line
            # if not output_started:
                    # add a newline after 'connecting' is done
                    # print('')
            output_started = True
            line = line.strip()
            if line.startswith('\x00'):
                # DO NOT USE THIS "try" in production -- Worker's "error"
                # signal will catch the exception and send it back for logging
                # try:
                d = json.loads(buf)
                if type(d) is list:
                    # result of 'conda list'
                    status = True
                    pkgs = ['-'.join([pkg['name'], pkg['version']])
                            for pkg in d]
                    result = status, pkgs
                    break
                msg = d.get('message')
                progress = d.get('progress')
                status = d.get('success', False)
                if progress:
                    n = 100 * progress
                    pkg = d.get("fetch", '')
                    if progress_signal:
                        progress_signal.emit(pkg, n)
                    # else:
                        # print('{}: {}'.format(pkg, n))
                elif msg:
                    if msg.endswith('already installed.'):
                        pkgs = []
                        result = status, pkgs
                        break
                # else:
                    # print(line)
                buf = line.replace('\x00', '')
                # except:
                    # print('oops, possibly broken json:')
                    # print('------------------')
                    # print(buf)
                    # print('------------------')
            else:
                buf += line.replace('\x00', '') + '\n'
    return result


if __name__ == '__main__':
    if len(sys.argv) > 1:
        pkg_name = sys.argv[1]
        run_conda(['install', '--json', '-y', pkg_name])
    else:
        print('Usage:  process_runner.py [conda pkg to install]')

