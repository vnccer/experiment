from agentdojo.task_suite import register_suite

from .tasks import task_suite

benchmark_version = "campus_security"
register_suite(task_suite, benchmark_version)
