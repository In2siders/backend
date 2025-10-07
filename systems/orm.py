

from peewee import CharField, TextField, UUIDField, ForeignKeyField, IPField
from db import BaseModel

# User model
class User(BaseModel):
    userId      = UUIDField(primary_key=True) # User unique ID
    username    = CharField(unique=True) # User unique username
    pub_key     = CharField(index=True) # User unique public key
    bio         = TextField() # TODO: DO NOT IMPLEMENT YET.


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

# Membership model (M2M relation | User <-> Group)
class Membership(BaseModel):
    user = ForeignKeyField(User, backref='memberships')
    group = ForeignKeyField(Group, backref='memberships')

    class Meta:
        primary_key = False
        indexes = (
            (('user', 'group'), True), # Unique constraint on user and group
        )

# Attachments model
class Attachment(BaseModel):
    attachmentId = UUIDField(primary_key=True)
    file_url = CharField() # URL to S3 or other storage (Behind a CDN)
    file_name = CharField() # Original file name
    uploaded_by = ForeignKeyField(User, backref='attachments')
    uploaded_at = CharField() # Timestamp of upload

# Message schema
"""
Message request
{
    "sId": "sessionId",
    "body": "Encrypted message body",
    "attachmentIds": ["attachmentId1", "attachmentId2"], # Optional
    "to": "groupId" | "userId", # Recipient (group or user)
    "isGroup": true | false # Is the recipient a group?
}
"""
class Message(BaseModel):
    messageId = UUIDField(primary_key=True)
    body = TextField() # Encrypted message body
    sender = ForeignKeyField(User, backref='sent_messages')
    to_group = ForeignKeyField(Group, null=True, backref='messages') # Nullable for direct messages
    to_user = ForeignKeyField(User, null=True, backref='received_messages') # Nullable for group messages
    timestamp = CharField() # Timestamp of the message