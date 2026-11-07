# source this to point the live-broker tests at docker-compose.brokers.yml
export AUSTIAL_TEST_REDIS_URL=redis://localhost:6379
export AUSTIAL_TEST_NATS_URL=nats://localhost:4222
export AUSTIAL_TEST_RABBITMQ_URL=amqp://guest:guest@localhost:5672/
export AUSTIAL_TEST_MONGO_URL=mongodb://localhost:27017
export AUSTIAL_TEST_MQTT_URL=localhost:1883
export AUSTIAL_TEST_KAFKA_URL=localhost:9092
