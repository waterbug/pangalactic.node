from __future__ import print_function
from builtins import range
from PyQt5.QtWidgets import (QApplication, QDialog, QMainWindow, QVBoxLayout,
                             QLabel, QProgressBar, QPushButton, QWidget)
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QRunnable,
                          QThreadPool, QTimer)

import time
import traceback, sys

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
            args: Arguments to pass to the callback function

        Keyword Args:
            kwargs: Keyword args to pass to the callback function
        """
        super(Worker, self).__init__()
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


# NOTE:  this "MainWindow" is just some example code to demonstrate usage ...
class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
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
            progress_signal.emit('stuff', n*100/4)
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

