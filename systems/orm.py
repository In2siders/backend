import datetime as dt
import os
import uuid
from peewee import CharField, TextField, UUIDField, ForeignKeyField, IPField, ManyToManyField, Model, BooleanField, DateTimeField, CompositeKey
from systems.db import db

# Base model
class BaseModel(Model):
    class Meta:
        database = db

datetime = dt.datetime
td = dt.timedelta
utc = dt.timezone.utc
utcn = lambda: datetime.now(utc)

# ==============
# ORM Structures
# ==============

# TODO: Create a table called 'PublicKeys' to store user public_keys, being id as keywords of 9 characters and with a fk to userId.

# User model
class User(BaseModel):
    userId      = UUIDField(primary_key=True, default=uuid.uuid4) # User unique ID
    username    = CharField(unique=True) # User unique username
    pub_key     = TextField(index=True) # User unique public key
    bio         = TextField(default="No bio yet!") # TODO: DO NOT IMPLEMENT YET.
    canLogin    = BooleanField(default=True)

# Challenge
class Challenge(BaseModel):
    challengeId = UUIDField(primary_key=True, default=uuid.uuid4)
    user = ForeignKeyField(User, backref='challenges', index=True)
    solution = CharField() # Challenge solution
    expires_at = CharField() # Expiration timestamp

# User session
class Session(BaseModel):
    sessionId = CharField(primary_key=True, default=uuid.uuid4)
    user = ForeignKeyField(User, backref='sessions')
    userIp = IPField()
    fingerprint = CharField(index=True)

# Group model
class Group(BaseModel):
    groupId = UUIDField(primary_key=True, default=uuid.uuid4)
    groupName = CharField(unique=True)
    description = TextField() # TODO: WAITING FOR FRONTEND DESIGN.
    owner = ForeignKeyField(User, backref='owned_groups')
    members = ManyToManyField(User, backref='groups')
    image = TextField(null=True)

# Membership model (M2M relation | User <-> Group)
class Membership(BaseModel):
    group = ForeignKeyField(Group, backref='members')
    user = ForeignKeyField(User, backref='memberships')
    encrypted_groupkey = TextField()
    groupRole = CharField(default='member')
    joined_at = DateTimeField(default=lambda: datetime.now(utc))
    updated_at = DateTimeField(default=lambda: datetime.now(utc))

    class Meta:
        primary_key = CompositeKey('group', 'user')
        indexes = (
            (('group', 'user'), True), # Unique constraint on groupId and userId
        )

# Message schema
class Message(BaseModel):
    messageId = UUIDField(primary_key=True, default=uuid.uuid4)
    body = TextField() # Encrypted message body
    sender = ForeignKeyField(User, backref='sent_messages')
    timestamp = CharField() # Timestamp of the message
    chatid = TextField()

# Attachments model
class Attachment(BaseModel):
    attachmentId = UUIDField(primary_key=True, default=uuid.uuid4)
    file_url = CharField() # URL to S3 or other storage (Behind a CDN)
    file_name = CharField() # Original file name
    uploaded_by = ForeignKeyField(User, backref='attachments')
    uploaded_at = CharField() # Timestamp of upload
    message = ForeignKeyField(Message, backref='attachments', null=True)

# Message transport
class MessageTransport(BaseModel):
    message = ForeignKeyField(Message, backref='transports')
    source = ForeignKeyField(User, backref='sent_transports', null=True)
    target = TextField()

    class Meta:
        primary_key = False
        indexes = (
            (('source', 'target', 'message'), True), # Unique constraint on source, target, and message
        )

# Group invitations
class GroupInvitations(BaseModel):
    invitationId = TextField(primary_key=True, default=lambda: os.urandom(24).hex())
    group = ForeignKeyField(Group, backref='invitations')
    expires_at = DateTimeField(default=lambda: utcn()+td(days=3))
    encrypted_groupkey = TextField()

def orm_get_all_models():
    import warnings
    warnings.warn("We have our greate friend Gurasic that tried to use this function, but it is NOT RECOMMENDED to use it outside of 'initialize_db()' function. So, this will be removed in the future (3 days max.)", DeprecationWarning, stacklevel=2)
    return [User, Challenge, Session, Group, Membership, Message, Attachment, MessageTransport]

def create_init_data():
    try:
        with db.atomic():
            if not User.select().where(User.username == "Deleted Account").exists():
                User.create(userId=uuid.UUID(bytes=b'\x00'*16), username="Deleted Account", pub_key="", canLogin=False)
        print("[*] Initial data created.")
        return True
    except Exception as e:
        print("[- ERROR -] Failed to create initial data:", e)
        return False

def initialize_db():
    try:
        if not db.is_closed():
            db.close()

        # Apply any pending migrations (creates tables via migration files)
        from migrate import cmd_init, cmd_migrate
        cmd_init()      # Ensures _migrations table + migrations/ dir exist
        cmd_migrate()   # Applies all pending .json migration files

        # Fallback: create any tables not yet covered by migrations (safe=True is a no-op if they exist)
        db.create_tables([User, Challenge, Session, Group, Membership, Message, Attachment, MessageTransport, GroupInvitations], safe=True)

        create_init_data()

        print("[*] Database initialized and migrations applied.")
        return True
    except Exception as e:
        print("[- ERROR -] Failed to initialize database:", e)
        return False