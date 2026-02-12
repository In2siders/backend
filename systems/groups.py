import os

from systems.db import db, DoesNotExist
from systems.orm import Group, Membership, GroupInvitations, User

def create_group(name, owner, encrypted_groupkey):
    owner_user = User.get(User.userId == owner.userId)
    if not owner_user:
        raise ValueError("We didn't find the owner in our database. Please make sure you are logged in and try again.")

    try:
        with db.atomic():
            new_group = Group.create(groupName=name, owner=owner_user, description="No description yet.")
            Membership.create(group=new_group, user=owner_user, encrypted_groupkey=encrypted_groupkey, groupRole='owner')
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
        membership = Membership.get((Membership.group == group) & (Membership.user == user) & (Membership.groupRole == 'owner'))
        if not membership:
            raise ValueError("Only the group owner can generate invite codes.")

        invite = GroupInvitations.create(group=group, encrypted_groupkey=encrypted_groupkey)
        return invite.invitationId
    except DoesNotExist:
        raise ValueError("Failed to generate invite code: User or group does not exist.")
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
        existing_membership = Membership.get_or_none((Membership.group == group) & (Membership.user == user))
        if existing_membership:
            raise ValueError("You are already a member of this group.")

        Membership.create(group=group, user=user, encrypted_groupkey=encrypted_groupkey, groupRole='member')
    except DoesNotExist:
        raise ValueError("Failed to join group: User, invite code, or group does not exist.")
    except Exception as e:
        raise ValueError(f"Failed to join group with invite code: {str(e)}")

def get_user_encrypted_groupkeys(user):
    # Placeholder for retrieving user's encrypted group keys logic
    pass