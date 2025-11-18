from __future__ import annotations

from typing import Optional, Sequence, cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.api_key import APIKey
from src.domain.repositories.api_key_repository import APIKeyRepository
from src.infrastructure.database.models import APIKeyModel


class SQLAlchemyAPIKeyRepository(APIKeyRepository):
    """SQLAlchemy-backed persistence for API credentials."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, api_key: APIKey) -> APIKey:
        model = APIKeyModel(
            user_id=api_key.user_id,
            exchange=api_key.exchange.lower(),
            access_key=api_key.access_key,
            secret_key=api_key.secret_key,
            passphrase=api_key.passphrase,
            label=api_key.label,
            is_active=api_key.is_active,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(self, api_key: APIKey) -> APIKey:
        if api_key.id is None:
            raise ValueError("API key identifier is required for update")
        model = await self.session.get(APIKeyModel, api_key.id)
        if not model:
            raise ValueError("API key not found")
        model.exchange = api_key.exchange.lower()
        model.access_key = api_key.access_key
        model.secret_key = api_key.secret_key
        model.passphrase = api_key.passphrase
        model.label = api_key.label
        model.is_active = api_key.is_active
        model.updated_at = api_key.updated_at
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def delete(self, api_key_id: int) -> None:
        await self.session.execute(
            delete(APIKeyModel).where(APIKeyModel.id == api_key_id)
        )
        await self.session.commit()

    async def get_by_id(self, api_key_id: int) -> Optional[APIKey]:
        model = await self.session.get(APIKeyModel, api_key_id)
        return self._to_entity(model) if model else None

    async def get_for_user(self, user_id: int) -> Sequence[APIKey]:
        result = await self.session.execute(
            select(APIKeyModel).where(APIKeyModel.user_id == user_id)
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def find_active_for_exchange(self, user_id: int, exchange: str) -> Optional[APIKey]:
        result = await self.session.execute(
            select(APIKeyModel)
            .where(APIKeyModel.user_id == user_id)
            .where(APIKeyModel.exchange == exchange.lower())
            .where(APIKeyModel.is_active.is_(True))
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    def _to_entity(self, model: APIKeyModel) -> APIKey:
        return APIKey(
            id=cast(int, model.id),
            user_id=cast(int, model.user_id),
            exchange=cast(str, model.exchange),
            access_key=cast(str, model.access_key),
            secret_key=cast(str, model.secret_key),
            passphrase=model.passphrase,
            label=model.label,
            is_active=cast(bool, model.is_active),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
