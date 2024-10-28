import concurrent.futures
import logging
import queue
from queue import Queue
from typing import Any, Callable, Generic, List, Optional, Type, TypeVar, cast

log = logging.getLogger(__name__)

WorkerContext = TypeVar("WorkerContext")
TaskContext = TypeVar("TaskContext")


class Worker(Generic[WorkerContext, TaskContext]):
    """
    A worker that processes tasks from a queue.

    Args:
        context (WorkerContext): The context for the worker.
        work (Callable[[WorkerContext, TaskContext], None]): A function that processes
            a task.
        evict_hook (Callable[[WorkerContext], None]): A function that is called when
            the worker is evicted.

    """

    def __init__(
        self,
        context: WorkerContext,
        work: Callable[[WorkerContext, TaskContext], None],
        evict_hook: Callable[[WorkerContext], None] = lambda x: None,
    ):
        """
        Initialize the Worker with a context, a work function, and an evict hook.

        Args:
            context (WorkerContext): The context for the worker.
            work (Callable[[WorkerContext, TaskContext], None]): A function that
                processes a task.
            evict_hook (Callable[[WorkerContext], None]): A function that is called when
                the worker is evicted.
        """
        self.context = context
        self.work = work
        self.evict_hook = evict_hook


class QueueProcessor(Generic[WorkerContext, TaskContext]):
    """
    A queue with a list of workers that process tasks from the queue.
    If a worker fails, the task is re-added to the queue, and the worker is evicted.
    Another worker will pick up the task. This is useful for processing tasks in parallel
    where some tasks may fail due to network issues or other reasons.
    """

    def __init__(
        self, evict_exceptions: List[Type[Exception]] | None = None, logger: Any = log
    ):
        """
        Initialize the QueueProcessor with a queue and a list of workers.

        Args:
            evict_exceptions (List[Type[Exception]]): A list of exceptions upon which
            workers from the worker list get evicted.
            logger (Any): The logger to use for logging.
        """
        if evict_exceptions is None:
            evict_exceptions = []

        self.queue: Queue[TaskContext] = Queue()
        self.workers: List[Worker[WorkerContext, TaskContext]] = []
        self.evict_exceptions = evict_exceptions
        self.log = logger

    def add_task(self, task: TaskContext) -> None:
        """
        Add a task to the queue.

        Args:
            task (TaskContext): The task to add.

        Returns:
            None
        """
        self.queue.put(task)

    def add_worker(self, worker: Worker[WorkerContext, TaskContext]) -> None:
        """
        Add a worker to the list of workers.

        Args:
            worker (Worker[WorkerContext, TaskContext]): The worker to add.

        Returns:
            None
        """
        self.workers.append(worker)

    def _start_worker_loop(self, worker: Worker[WorkerContext, TaskContext]) -> None:
        """
        Start a worker loop and process the queue until it is empty.

        Args:
            worker (Worker[WorkerContext, TaskContext]): The worker to use.

        Returns:
            None
        """
        while not self.queue.empty():
            task: Optional[TaskContext] = None
            try:
                task = self.queue.get(block=False)
                worker.work(worker.context, task)
                self.queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                self.queue.put(cast(TaskContext, task))
                self.queue.task_done()
                raise e

    def _exhaust_queue_with_worker(
        self, worker: Worker[WorkerContext, TaskContext]
    ) -> None:
        """
        Start a worker loop and process the queue until it is empty.

        Args:
            worker (Worker[WorkerContext, TaskContext]): The worker to use.

        Returns:
            None
        """
        while self.queue.unfinished_tasks > 0:
            try:
                self._start_worker_loop(worker)
            except Exception as e:
                self.log.error(
                    f"Worker: {worker} failed, no longer using it: {e}"
                    f" - unfinished tasks: {self.queue.unfinished_tasks}"
                )
                worker.evict_hook(worker.context)
                self.log.debug(f"Error: {e}")
                break

    def process(self) -> None:
        """
        Start a thread pool with the workers and process the queue.
        """
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(self.workers)
        ) as executor:
            futures = [
                executor.submit(self._exhaust_queue_with_worker, worker)
                for worker in self.workers
            ]
            for future in futures:
                future.result()
