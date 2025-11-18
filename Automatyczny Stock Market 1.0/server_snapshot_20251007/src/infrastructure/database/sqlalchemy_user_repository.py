"""SQLAlchemy implementation of User repository."""

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User, UserRole
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.database.models import UserModel


class SQLAlchemyUserRepository(UserRepository):
    """SQLAlchemy implementation of UserRepository."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def create(self, user: User) -> User:
        """Create a new user in database."""
        db_user = UserModel(
            email=user.email,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        self.session.add(db_user)
        await self.session.commit()
        await self.session.refresh(db_user)
        return self._to_entity(db_user)

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID from database."""
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email from database."""
        result = await self.session.execute(select(UserModel).where(UserModel.email == email))
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username from database."""
        result = await self.session.execute(select(UserModel).where(UserModel.username == username))
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def update(self, user: User) -> User:
        """Update existing user in database."""
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
                last_login=user.last_login,
            )
        )
        await self.session.commit()
        return user

    async def delete(self, user_id: int) -> bool:
        """Delete user from database."""
        result = await self.session.execute(delete(UserModel).where(UserModel.id == user_id))
        await self.session.commit()
        return result.rowcount > 0

    async def list_active_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        """List active users with pagination."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.is_active).limit(limit).offset(offset)
        )
        db_users = result.scalars().all()
        return [self._to_entity(db_user) for db_user in db_users]

    def _to_entity(self, db_user: UserModel) -> User:
        """Convert database model to domain entity."""
        return User(
            id=db_user.id,
            email=db_user.email,
            username=db_user.username,
            password_hash=db_user.password_hash,
            role=UserRole(db_user.role),
            is_active=db_user.is_active,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
            last_login=db_user.last_login,
        )
