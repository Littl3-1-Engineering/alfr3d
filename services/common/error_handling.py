import logging

logger = logging.getLogger(__name__)


def handle_db_error(e: Exception, db, operation: str, reraise: bool = False) -> None:
    """Handle database errors with proper logging and rollback."""
    logger.error(f"Database error during {operation}: {e}")
    if db:
        try:
            db.rollback()
            logger.info(f"Transaction rolled back for {operation}")
        except Exception as rollback_error:
            logger.error(f"Failed to rollback transaction: {rollback_error}")
    if reraise:
        raise


def handle_kafka_error(e: Exception, operation: str) -> None:
    """Handle Kafka errors with proper logging."""
    from kafka.errors import KafkaError

    if isinstance(e, KafkaError):
        logger.error(f"Kafka error during {operation}: {e}")
    else:
        logger.error(f"Error during {operation}: {e}")


def handle_api_error(e: Exception, operation: str) -> tuple:
    """Handle API errors, returning error response tuple."""
    logger.error(f"API error during {operation}: {e}")
    return {"error": str(e)}, 500
