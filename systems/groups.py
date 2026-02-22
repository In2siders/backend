import os
import datetime as dt

from systems.db import db, DoesNotExist
from systems.orm import Group, Membership, GroupInvitations, User

utc = dt.timezone.utc


def create_group(name, owner, encrypted_groupkey, imageKey):
    owner_user = User.get(User.userId == owner.userId)
    if not owner_user:
        raise ValueError(
            "We didn't find the owner in our database. Please make sure you are logged in and try again."
        )

    try:
        with db.atomic():
            new_group = Group.create(
                groupName=name,
                owner=owner_user,
                description="No description yet.",
                image=imageKey,
            )
            Membership.create(
                group=new_group,
                user=owner_user,
                encrypted_groupkey=encrypted_groupkey,
                groupRole="owner",
            )
    except Exception as e:
        raise ValueError(f"An error occurred while creating the group: {str(e)}")

    return new_group


def generate_group_invite_code(group_id, user, encrypted_groupkey):
    try:
        user = User.get(User.userId == user.userId)
        if not user:
            raise ValueError("User not found.")

        group = Group.get(Group.groupId == group_id)
        if not group:
            raise ValueError("Group not found.")

        # Check if the user is the owner of the group
        membership = Membership.get(
            (Membership.group == group)
            & (Membership.user == user)
            & (Membership.groupRole == "owner")
        )
        if not membership:
            raise ValueError("Only the group owner can generate invite codes.")

        invite = GroupInvitations.create(
            group=group, encrypted_groupkey=encrypted_groupkey
        )
        return invite.invitationId
    except DoesNotExist:
        raise ValueError(
            "Failed to generate invite code: User or group does not exist."
        )
    except Exception as e:
        raise ValueError(f"Failed to generate invite code: {str(e)}")
    pass


def join_group_with_invite_code(invite_code, user, encrypted_groupkey):
    try:
        user = User.get(User.userId == user.userId)
        if not user:
            raise ValueError("User not found.")

        invite = GroupInvitations.get(GroupInvitations.invitationId == invite_code)
        if not invite:
            raise ValueError("Invalid invite code.")

        group = invite.group
        if not group:
            raise ValueError("Group associated with the invite code not found.")

        # Check if the user is already a member of the group
        existing_membership = Membership.get_or_none(
            (Membership.group == group) & (Membership.user == user)
        )
        if existing_membership:
            raise ValueError("You are already a member of this group.")

        Membership.create(
            group=group,
            user=user,
            encrypted_groupkey=encrypted_groupkey,
            groupRole="member",
        )
    except DoesNotExist:
        raise ValueError(
            "Failed to join group: User, invite code, or group does not exist."
        )
    except Exception as e:
        raise ValueError(f"Failed to join group with invite code: {str(e)}")


def get_group_invite_payload(invite_code):
    try:
        invite = GroupInvitations.get(GroupInvitations.invitationId == invite_code)
        if not invite:
            raise ValueError("Invalid invite code.")

        if invite.expires_at < dt.datetime.now(utc):
            raise ValueError("Invite code has expired.")

        return {
            "inviteCode": invite.invitationId,
            "groupId": str(invite.group.groupId),
            "encryptedGroupKey": invite.encrypted_groupkey,
            "expiresAt": invite.expires_at.isoformat(),
        }
    except DoesNotExist:
        raise ValueError("Invite code does not exist.")
    except Exception as e:
        raise ValueError(f"Failed to read invite code: {str(e)}")


def get_user_memberships(user):
    try:
        user = User.get(User.userId == user.userId)
        if not user:
            raise ValueError("User not found.")

        memberships = Membership.select().where(Membership.user == user)
        return memberships
    except DoesNotExist:
        raise ValueError("Failed to retrieve memberships: User does not exist.")
    except Exception as e:
        raise ValueError(f"Failed to retrieve memberships: {str(e)}")


def get_group_metadata(user, group_id):
    try:
        user = User.get(User.userId == user.userId)
        if not user:
            raise ValueError("User not found.")

        group = Group.get(Group.groupId == group_id)
        if not group:
            raise ValueError("Group not found.")

        membership = Membership.get(
            (Membership.user == user) & (Membership.group == group)
        )
        if not membership:
            raise ValueError("You are not a member of this group.")

        members = Membership.select().where(Membership.group == group)

        return group, membership, members
    except DoesNotExist:
        raise ValueError(
            "Failed to retrieve group metadata: User or group does not exist."
        )
    except Exception as e:
        raise ValueError(f"Failed to retrieve group metadata: {str(e)}")


def get_user_membership_by_group(user, group_id):
    """idk, created if it works on a future, now there is no usage..."""
    try:
        user = User.get(User.userId == user.userId)
        if not user:
            raise ValueError("User not found.")

        group = Group.get(Group.groupId == group_id)
        if not group:
            raise ValueError("Group not found.")

        membership = Membership.get(
            (Membership.user == user) & (Membership.group == group)
        )
        return membership
    except DoesNotExist:
        raise ValueError("Failed to retrieve membership: User or group does not exist.")
    except Exception as e:
        raise ValueError(f"Failed to retrieve membership: {str(e)}")


def update_group_settings(group_id, user, new_name=None, image_key=None):
    try:
        db_user = User.get(User.userId == user.userId)
        if not db_user:
            raise ValueError("User not found.")

        group = Group.get(Group.groupId == group_id)
        if not group:
            raise ValueError("Group not found.")

        membership = Membership.get_or_none(
            (Membership.group == group) & (Membership.user == db_user)
        )
        if not membership:
            raise ValueError("You are not a member of this group.")

        if membership.groupRole != "owner":
            raise ValueError("Only the group owner can update group settings.")

        if new_name:
            group.groupName = new_name

        if image_key is not None:
            group.image = image_key

        group.save()
        return group
    except DoesNotExist:
        raise ValueError(
            "Failed to update group settings: User or group does not exist."
        )
    except Exception as e:
        raise ValueError(f"Failed to update group settings: {str(e)}")


def leave_group(group_id, user):
    try:
        db_user = User.get(User.userId == user.userId)
        if not db_user:
            raise ValueError("User not found.")

        group = Group.get(Group.groupId == group_id)
        if not group:
            raise ValueError("Group not found.")

        membership = Membership.get_or_none(
            (Membership.group == group) & (Membership.user == db_user)
        )
        if not membership:
            raise ValueError("You are not a member of this group.")

        if membership.groupRole == "owner":
            members_count = Membership.select().where(Membership.group == group).count()
            if members_count > 1:
                raise ValueError(
                    "Owner cannot leave while members are still in the group."
                )

        with db.atomic():
            Membership.delete().where(
                (Membership.group == group) & (Membership.user == db_user)
            ).execute()
            if membership.groupRole == "owner":
                Group.delete().where(Group.groupId == group.groupId).execute()

        return True
    except DoesNotExist:
        raise ValueError("Failed to leave group: User or group does not exist.")
    except Exception as e:
        raise ValueError(f"Failed to leave group: {str(e)}")
