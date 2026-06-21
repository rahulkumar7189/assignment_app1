from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/acadmate")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "acadmate")

motor_client: AsyncIOMotorClient = None


async def init_db():
    global motor_client
    from models import (
        User, HelpRequest, Message, Review, ActivityLog, Notification,
        PaymentDetection, SystemSettings, Milestone, Dispute,
        MarketplaceItem, RazorpayOrder,
    )
    motor_client = AsyncIOMotorClient(MONGO_URL)
    await init_beanie(
        database=motor_client[MONGO_DB_NAME],
        document_models=[
            User, HelpRequest, Message, Review, ActivityLog, Notification,
            PaymentDetection, SystemSettings, Milestone, Dispute,
            MarketplaceItem, RazorpayOrder,
        ],
    )


def get_motor_client() -> AsyncIOMotorClient:
    return motor_client
