from peewee import CharField, TextField, UUIDField, ForeignKeyField, IPField, ManyToManyField
from db import BaseModel

# User model
class User(BaseModel):
    userId      = UUIDField(primary_key=True) # User unique ID
    username    = CharField(unique=True) # User unique username
    pub_key     = CharField(index=True) # User unique public key
    bio         = TextField(default="No bio yet!") # TODO: DO NOT IMPLEMENT YET.


# User session
class Session(BaseModel):
    sessionId = CharField(primary_key=True)
    user = ForeignKeyField(User, backref='sessions')
    userIp = IPField()

# Group model
class Group(BaseModel):
    groupId = UUIDField(primary_key=True)
    groupName = CharField(unique=True)
    description = TextField() # TODO: WAITING FOR FRONTEND DESIGN.
    owner = ForeignKeyField(User, backref='owned_groups')
    group_key = CharField() # Symmetric key for the group
    members = ManyToManyField(User, backref='groups')

# Membership model (M2M relation | User <-> Group)
Membership = Group.members.get_through_model() 

# Attachments model
class Attachment(BaseModel):
    attachmentId = UUIDField(primary_key=True)
    file_url = CharField() # URL to S3 or other storage (Behind a CDN)
    file_name = CharField() # Original file name
    uploaded_by = ForeignKeyField(User, backref='attachments')
    uploaded_at = CharField() # Timestamp of upload

# Message schema
class Message(BaseModel):
    messageId = UUIDField(primary_key=True)
    body = TextField() # Encrypted message body
    sender = ForeignKeyField(User, backref='sent_messages')
    timestamp = CharField() # Timestamp of the message

# Message transport
class MessageTransport(BaseModel):
    message = ForeignKeyField(Message, backref='transports')
    source = ForeignKeyField(User, backref='sent_transports', null=True)
    target = ForeignKeyField(User, backref='received_messages', null=True)

    class Meta:
        primary_key = False
        indexes = (
            (('source', 'target', 'message'), True), # Unique constraint on source, target, and message
        )

def orm_get_all_models():
    return [User, Session, Group, Membership, Attachment, Message, MessageTransport]