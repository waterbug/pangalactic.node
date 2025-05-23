#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Thread-related functions
"""
import os, time, traceback, sys
from functools import partial

from pydispatch import dispatcher

from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QLabel,
                             QProgressBar, QPushButton, QWidget)
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QRunnable,
                          QThreadPool, QTimer)

from pangalactic.core.smerializers import deserialize


threadpool = QThreadPool.globalInstance()


class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        `tuple` (exctype, value, traceback.format_exc() )

    result
        `object` data returned from processing, anything

    progress
        `str`, `int`: what(str), % progress(int)

    '''
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(str, int)


class Worker(QRunnable):
    """
    Inherits from QRunnable to handle worker thread setup, signals and wrap-up.
    """

    def __init__(self, fn, *args, **kwargs):
        """
        Initialize Worker.

        Args:
            fn: The function to be called
            args: Arguments to pass to the callback function

        Keyword Args:
            kwargs: Keyword args to pass to the callback function
        """
        super().__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the signal object for 'progress' to kwargs:  it will be passed
        # to the callback function, which will use it to emit progress signals
        kwargs['progress_signal'] = self.signals.progress

    @pyqtSlot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            # traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()

# ----------------------------------------------------------------------------
# NOTE:  Running the UberOrb-based serializers.deserializer() function in a
# separate thread is not possible because sqlite objects cannot be used from a
# thread other than the one in which they were created.
# ----------------------------------------------------------------------------


def run_deserializer(*args, **kwargs):
    """
    Run the smerializers.deserialize() function -- this wrapper is designed to
    be run by a Worker so deserialization can be done in a separate thread from
    the gui and emit progress signals that update a progress dialog.

    Args:
        args (tuple):  arguments to deserialize()

    Keyword Args:
        progress_signal (pyqtSignal): signal object (passed in by the Worker
            instance that calls this function.
    """
    progress_signal = kwargs.get('progress_signal')
    if progress_signal:
        del kwargs['progress_signal']
    else:
        return
    def send_progress_update(msg, n):
        progress_signal.emit(msg, n)
    dispatcher.connect(send_progress_update, 'deserialized object')
    deserialize(*args, **kwargs)


def run_chunkify_file(fpath, chunk_size, **kwargs):
    """
    Chunkify a file -- this function is designed to be run by a Worker so the
    chunkification can be done in a separate thread from the gui and emit
    progress signals that update a progress dialog.

    Args:
        fpath (str):  path of the file to chunkify
        chunk_size (int):  the size of the chunks

    Keyword Args:
        progress_signal (pyqtSignal): signal object (passed in by the Worker
            instance that calls this function.
    """
    progress_signal = kwargs.get('progress_signal')
    if progress_signal:
        del kwargs['progress_signal']
    else:
        return
    def send_progress_update(msg, n):
        progress_signal.emit(msg, n)
    return chunkify_file(fpath, chunk_size, progress_signal)


def chunkify_file(fpath, chunk_size, progress_signal):
    chunks = []
    fsize = os.path.getsize(fpath)
    with open(fpath, 'rb') as f:
        for chunk in iter(partial(f.read, chunk_size), b''):
            chunks.append(chunk)
            p = (len(chunks) * chunk_size * 100) // fsize
            progress_signal.emit('', p)
    return chunks


# NOTE:  this "MainWindow" is just some example code to demonstrate usage ...
class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = 0
        layout = QVBoxLayout()
        self.l = QLabel("Start")
        self.t = QLabel("Thing being updated")
        b = QPushButton("DANGER!")
        b.pressed.connect(self.oh_no)
        layout.addWidget(self.l)
        layout.addWidget(self.t)
        layout.addWidget(b)
        self.progress_bar = QProgressBar(self)
        # min and max both set to 0 initially so progress bar "spins" until
        # the first signal is received from the process
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)
        layout.addWidget(self.progress_bar)
        w = QWidget()
        w.setLayout(layout)
        self.setCentralWidget(w)
        self.show()
        # self.threadpool = QThreadPool.globalInstance()
        print("Multithreading with maximum {} threads".format(
              threadpool.maxThreadCount()))
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.recurring_timer)
        self.timer.start()

    def progress_fn(self, what, n):
        """
        Set max and value for progress bar.

        Args:
            what (str):  thing being updated
            n (float): progress as a fraction (<= 1.0)
        """
        print("{}: {}% done".format(what, n))
        self.t.setText("{} updating ...".format(what))
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(n)

    def execute_this_fn(self, progress_signal):
        for n in range(0, 5):
            time.sleep(1)
            progress_signal.emit('stuff', n*100//4)
        return "Done."

    def print_output(self, s):
        self.t.setText(s)
        print(s)

    def thread_complete(self):
        print("THREAD COMPLETE!")

    def oh_no(self):
        # Pass the function to execute
        # Any other args, kwargs are passed to the run function
        worker = Worker(self.execute_this_fn)
        worker.signals.result.connect(self.print_output)
        worker.signals.finished.connect(self.thread_complete)
        worker.signals.progress.connect(self.progress_fn)
        # Execute
        threadpool.start(worker)

    def recurring_timer(self):
        self.counter +=1
        self.l.setText("Counter: %d" % self.counter)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

