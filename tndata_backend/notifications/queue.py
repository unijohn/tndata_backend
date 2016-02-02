from datetime import timedelta
from django.utils import timezone

import django_rq


def get_scheduler(queue='default'):
    return django_rq.get_scheduler('default')

scheduler = get_scheduler()


def send(message_id):
    """Given an ID for a GCMMessage object, send the message via GCM."""
    from . models import GCMMessage
    msg = GCMMessage.objects.get(pk=message_id)
    msg.send()
    # TODO: Record a metric


def enqueue(message, threshold=24):
    """Given a GCMMessage object, add it to the queue of messages to be sent."""

    job = None
    now = timezone.now()
    threshold = now + timedelta(hours=threshold)

    # Only queue up messages for the next 24 hours
    if now < message.deliver_on and message.deliver_on < threshold:
        job = scheduler.enqueue_at(message.deliver_on, send, message.id)
        message.queue_id = job.id
        message.save()

    # TODO: Record a metric so we can see queued vs sent?

    # TODO: save the job ID on the GCMMessage, so if it gets re-enqueued we
    # can cancel the original?

    return job


def messages():
    """Return a list of jobs that are scheduled with their scheduled times.

    Returned data is a list of (Job, datetime) tuples.

    """
    return scheduler.get_jobs(with_times=True)