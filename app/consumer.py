import threading
import json
import time

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from .reconcile import ReconciliationEngine

RETRY_TIME=2  # seconds


# FIX (Amsterdam release)
# Previously, the consumer attempted to connect to Kafka only once.
# If the Kafka broker was still starting, KafkaConsumer raised
# NoBrokersAvailable and the consumer thread terminated permanently.
#
# The consumer now retries the Kafka connection every 5 seconds until
# the broker becomes available. This prevents a Docker startup race
# where the TradeRecon container starts before Kafka is fully ready.


class TradeDataConsumer(threading.Thread):
    def __init__(self, topic: str, bootstrap_servers: str, group_id: str, reconcile_engine: ReconciliationEngine):
        super().__init__()
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.reconcile_engine = reconcile_engine
        self.running = True

        print(f"Initializing consumer for topic: {self.topic}, group_id: {self.group_id}, broker: {self.bootstrap_servers}")

    def run(self):
        consumer = None
        
        # Keep retrying until Kafka is ready instead of terminating
        # the consumer thread after the first NoBrokersAvailable error.
        while self.running and consumer is None:
            try:
                print(f"Connecting {self.topic} consumer to {self.bootstrap_servers}...")
                
                consumer = KafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.group_id,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='earliest',
                    enable_auto_commit=True,
                )
                
                print(f"Consumer for topic '{self.topic}' connected successfully.")
                
            except NoBrokersAvailable:
                # Docker may have started the Kafka container, but Kafka
                # itself may still be initializing and not accepting connections.
                # Wait and retry rather than allowing this thread to die.
                print(f"Kafka unavailable for '{self.topic}'. Retrying in {RETRY_TIME} seconds...")
                time.sleep(RETRY_TIME)

            except Exception as e:
                print(f"Error in consumer for topic {self.topic}: {e}")
            
        if consumer is not None:    
            return
        try:
            for message in consumer:
                if not self.running:
                    break
                print(f"Received message from topic '{self.topic}': {message.value}")
                self.reconcile_engine.process_message(self.topic, message.value)
        
        except Exception as e:
            print(f"Error while consuming messages from topic {self.topic}: {e}")
        
        finally:
            if consumer is not None:
                consumer.close()
                print(f"Consumer for topic '{self.topic}' closed.")            
            
    def stop(self):
        self.running = False
