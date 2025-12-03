"""Generic daemon class for managing background processes in ALFR3D."""

import sys
import os
import time
import atexit
import logging
from signal import SIGTERM


# set up logging
logger = logging.getLogger("DaemonLifecycle")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


class Daemon:
    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    """

    def __init__(
        self,
        pidfile: str,
        stdin: str = "/dev/stdin",
        stdout: str = "/dev/stdout",
        stderr: str = "/dev/stderr",
    ) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        logger.info("Starting daemonization process")
        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                logger.info("First parent exiting after fork")
                sys.exit(0)
        except OSError as e:
            logger.error("Fork #1 failed: %d (%s)" % (e.errno, e.strerror))
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)
        logger.info("Decoupled from parent environment")

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                logger.info("Second parent exiting after fork")
                sys.exit(0)
        except OSError as e:
            logger.error("Fork #2 failed: %d (%s)" % (e.errno, e.strerror))
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        logger.info("Redirected standard file descriptors")

        # write pidfile
        atexit.register(self.delpid)
        os.makedirs(os.path.dirname(self.pidfile), exist_ok=True)
        pid = str(os.getpid())
        open(self.pidfile, "w+").write("%s\n" % pid)
        logger.info("Daemonized successfully, PID: %s" % pid)

    def delpid(self) -> None:
        os.remove(self.pidfile)

    def start(self) -> None:
        """
        Start the daemon
        """
        logger.info("Attempting to start daemon")
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = open(self.pidfile, "r")
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            logger.error("Daemon already running with PID: %s" % pid)
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)

        # Start the daemon
        logger.info("Daemonizing and starting run loop")
        self.daemonize()
        logger.info("Daemon started, entering run loop")
        self.run()

    def stop(self) -> None:
        """
        Stop the daemon
        """
        logger.info("Attempting to stop daemon")
        # Get the pid from the pidfile
        try:
            pf = open(self.pidfile, "r")
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            logger.warning("No PID file found, daemon may not be running")
            sys.stderr.write(message % self.pidfile)
            return  # not an error in a restart

        # Try killing the daemon process
        logger.info("Sending SIGTERM to PID: %s" % pid)
        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError as err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
                logger.info("Daemon stopped successfully")
            else:
                logger.error("Error stopping daemon: %s" % str(err))
                print(str(err))
                sys.exit(1)

    def restart(self) -> None:
        """
        Restart the daemon
        """
        logger.info("Restarting daemon")
        self.stop()
        self.start()

    def run(self) -> None:
        """
        You should override this method when you subclass Daemon. It will be called after
        the process has been daemonized by start() or restart().
        """
