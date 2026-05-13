import sys
import threading

from .message_handler import MessageHandler
from .napcat_client import NapCatClient
from .logger import get_logger
from .task_manager import TaskManager

log = get_logger("bot")


def main():
    client = NapCatClient()
    tm = TaskManager(client)
    MessageHandler(client, tm)
    client.start()
    log.info("started, press Ctrl+C to stop")

    shutdown_event = threading.Event()
    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        log.info("shutting down...")
        client.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
