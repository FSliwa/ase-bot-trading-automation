from typing import Optional, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from src.domain.entities.user import User, UserRole
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.database.models import UserModel

class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: User) -> User:
        """Create new user in database."""
        db_user = UserModel(
            email=user.email,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )
        self.session.add(db_user)
        await self.session.commit()
        await self.session.refresh(db_user)
        return self._to_entity(db_user)

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        result = await self.session.execute(
            select(UserModel)
            .where(UserModel.id == user_id)
        )
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def update(self, user: User) -> User:
        """Update existing user in database."""
        if user.id is None:
            raise ValueError("User ID cannot be None for an update operation")
        await self.session.execute(
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(
                email=user.email,
                username=user.username,
                password_hash=user.password_hash,
                role=user.role.value,
                is_active=user.is_active,
                updated_at=user.updated_at,
                last_login_at=user.last_login_at,
            )
        )
        await self.session.commit()
        return user

    async def delete(self, user_id: int) -> None:
        """Delete user from database."""
        await self.session.execute(
            delete(UserModel)
            .where(UserModel.id == user_id)
        )
        await self.session.commit()

    async def list_active_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        """List active users with pagination."""
        result = await self.session.execute(
            select(UserModel)
            .where(UserModel.is_active)
            .limit(limit)
            .offset(offset)
        )
        db_users = result.scalars().all()
        return [self._to_entity(db_user) for db_user in db_users]

    def _to_entity(self, db_user: UserModel) -> User:
        """Convert database model to domain entity."""
        # This explicit cast is needed because SQLAlchemy columns are not seen as concrete types by mypy
        return User(
            id=cast(int, db_user.id),
            email=cast(str, db_user.email),
            username=cast(str, db_user.username),
            password_hash=cast(str, db_user.password_hash),
            role=UserRole(cast(str, db_user.role)),
            is_active=cast(bool, db_user.is_active),
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
            last_login_at=db_user.last_login_at,
        )
