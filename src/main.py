from pymilvus import connections, utility

MILVUS_HOST = "localhost"
MILVUS_PORT = 19530
MILVUS_ALIAS = "default"


def main():
    try:
        connections.connect(
            alias=MILVUS_ALIAS,
            host=MILVUS_HOST,
            port=MILVUS_PORT,
        )
        print("connected")

    except Exception as e:
        print("Failed to connect to Milvus:", e)
    finally:
        if connections.has_connection(MILVUS_ALIAS):
            connections.disconnect(MILVUS_ALIAS)
            print("closed")


if __name__ == "__main__":
    main()
