import json
import pika
import os


_rmq_connection = None
_rmq_channel = None

def _init_rmq():
    global _rmq_connection, _rmq_channel

    creds = pika.PlainCredentials(
        os.environ["RABBITMQ_USER"],
        os.environ["RABBITMQ_PASS"],
    )

    params = pika.ConnectionParameters(
        host=os.environ["RABBITMQ_HOST"],
        virtual_host=os.environ.get("RABBITMQ_VHOST", "/"),
        credentials=creds,
        heartbeat=60,
        blocked_connection_timeout=30,
    )

    _rmq_connection = pika.BlockingConnection(params)
    _rmq_channel = _rmq_connection.channel()

    exchange = os.environ.get("RABBITMQ_EXCHANGE", "forum.events")
    _rmq_channel.exchange_declare(
        exchange=exchange,
        exchange_type="topic",
        durable=True,
    )

def get_rmq_channel():
    global _rmq_connection, _rmq_channel

    if _rmq_connection is None or _rmq_channel is None or _rmq_channel.is_closed:
        _init_rmq()

    return _rmq_channel

def publish_event(routing_key: str, payload: dict) -> None:
    ch = get_rmq_channel()
    exchange = os.environ.get("RABBITMQ_EXCHANGE", "forum.events")

    body = json.dumps(payload).encode("utf-8")

    ch.basic_publish(
        exchange=exchange,
        routing_key=routing_key,
        body=body,
        properties=pika.BasicProperties(
            delivery_mode=2,              # persistent message
            content_type="application/json",
        ),
    )
