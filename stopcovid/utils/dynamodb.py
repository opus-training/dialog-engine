from boto3.dynamodb.types import TypeSerializer, TypeDeserializer


def serialize(a_dict):
    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in a_dict.items()}


def deserialize(a_dict):
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in a_dict.items()}
