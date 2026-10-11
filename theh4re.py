import os
import re
import traceback

import discord
from dotenv import load_dotenv

# Load .env from the same folder as this script, regardless of where it's run from
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # enable "Server Members Intent" in the developer portal

COMMAND_PREFIX = "oh hare"
# Never ping anyone from bot replies (@everyone, @here, roles, users)
client = discord.Client(
    intents=intents, allowed_mentions=discord.AllowedMentions.none()
)

HELP_COMMANDS = [
    (
        f"{COMMAND_PREFIX} create <name1> <name2> ... [in <category>]",
        "Create several text channels at once, optionally under a category.",
    ),
    (
        f"{COMMAND_PREFIX} delete <#channel> [#channel ...]",
        "Delete channels.",
    ),
    (
        f"{COMMAND_PREFIX} hide <category>",
        "Hide the category and all its channels from @everyone.",
    ),
    (
        f"{COMMAND_PREFIX} move <from category> to <to category>",
        "Move every channel in one category into another.",
    ),
    (
        f"{COMMAND_PREFIX} clear <category>",
        "Remove all permission overrides from every channel in the category.",
    ),
    (
        f"{COMMAND_PREFIX} allow <@role> <#channel> [#channel ...]",
        "Let a role view and message those channels.",
    ),
    (
        f"{COMMAND_PREFIX} embed [#channel] <title> | <text> | [image url]",
        "Send your own orange embed (attach an image or give a link).",
    ),
    (
        f"{COMMAND_PREFIX} assign <#voice-channel>",
        "Give everyone in that voice channel a role named after their username.",
    ),
    (
        f"{COMMAND_PREFIX} remove <#voice-channel>",
        "Take those roles back and delete them.",
    ),
]


ORANGE = discord.Color.from_rgb(255, 140, 0)
DIVIDER = "▰▱▰▱▰▱▰▱▰▱▰▱▰▱▰▱▰▱▰▱"


def make_embed(text, title="Oh Hare"):
    """Orange embed with stylistic borders around the text."""
    embed = discord.Embed(
        title=f"✦━━━ 🐇 {title} 🐇 ━━━✦",
        description=f"{DIVIDER}\n{text}\n{DIVIDER}",
        color=ORANGE,
    )
    embed.set_footer(text="🐇 oh hare  •  admins only")
    return embed


async def reply(message, text, title="Oh Hare"):
    return await message.channel.send(embed=make_embed(text, title))


def help_embed():
    embed = make_embed("Every command is for administrators only.", "Commands")
    for usage, desc in HELP_COMMANDS:
        embed.add_field(name=f"❖ `{usage}`", value=f"╰ {desc}", inline=False)
    return embed


class ConfirmView(discord.ui.View):
    """Confirm / Cancel buttons that only the invoking admin can press."""

    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the admin who ran the command can answer this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_button(self, interaction, button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction, button):
        self.value = False
        await interaction.response.defer()
        self.stop()


async def confirm(message, text):
    """Ask the invoking admin to confirm a destructive action. Returns True/False."""
    view = ConfirmView(message.author.id)
    prompt = await message.channel.send(
        embed=make_embed(
            f"⚠️ **Are you sure?**\n{text}\n\n*This cannot be undone. Expires in 30s.*",
            "Confirm",
        ),
        view=view,
    )
    await view.wait()
    if view.value:
        outcome = "✅ Confirmed. Working on it..."
    elif view.value is False:
        outcome = "✖️ Cancelled. Nothing was changed."
    else:
        outcome = "⌛ Timed out. Nothing was changed."
    await prompt.edit(embed=make_embed(outcome, "Confirm"), view=None)
    return bool(view.value)


def find_voice_channel(message, arg):
    """Resolve a voice channel from a mention, ID or name."""
    for ch in message.channel_mentions:
        if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
            return ch
    arg = arg.strip().lstrip("#")
    for ch in message.guild.voice_channels:
        if ch.name.lower() == arg.lower() or str(ch.id) == arg:
            return ch
    return None


def find_category(guild, arg):
    """Resolve a category by name or ID."""
    arg = arg.strip()
    return discord.utils.find(
        lambda c: c.name.lower() == arg.lower() or str(c.id) == arg, guild.categories
    )


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

    activity = discord.Activity(type=discord.ActivityType.listening, name="The Wolves")
    await client.change_presence(status=discord.Status.idle, activity=activity)



@client.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    content = message.content.strip()
    if not content.lower().startswith(COMMAND_PREFIX):
        return

    # Admins only (the server owner always counts as an administrator)
    if not message.author.guild_permissions.administrator:
        await reply(message, "Only administrators can use this bot.")
        return

    parts = content[len(COMMAND_PREFIX):].strip().split(maxsplit=1)
    if not parts:
        await message.channel.send(embed=help_embed())
        return
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    try:
        if cmd == "create":
            # Optional category: "... in <category name>"
            names_part, _, category_name = re.split(
                r"(\s+in\s+)", arg, maxsplit=1, flags=re.IGNORECASE
            ) if re.search(r"\s+in\s+", arg, re.IGNORECASE) else (arg, "", "")
            names = [n for n in names_part.replace(",", " ").split() if n]
            if not names:
                await reply(message, 
                    f"Usage: `{COMMAND_PREFIX} create <name1> <name2> ... [in <category>]`"
                )
                return
            if len(names) > 25:
                await reply(message, "Max 25 channels at once.")
                return
            category = None
            category_name = category_name.strip()
            if category_name:
                category = discord.utils.find(
                    lambda c: c.name.lower() == category_name.lower()
                    or str(c.id) == category_name,
                    message.guild.categories,
                )
                if category is None:
                    available = ", ".join(c.name for c in message.guild.categories) or "none"
                    await reply(message, 
                        f"Category **{category_name}** not found. Available: {available}"
                    )
                    return
            created = []
            for name in names:
                ch = await message.guild.create_text_channel(name, category=category)
                created.append(ch.mention)
            where = f" under **{category.name}**" if category else ""
            await reply(message, f"Created{where}: {' '.join(created)}")

        elif cmd == "delete":
            targets = list(message.channel_mentions)
            if not targets:
                ch = find_voice_channel(message, arg)
                targets = [ch] if ch else []
            if not targets:
                await reply(message, "Channel not found. Mention the channel(s) to delete.")
                return
            names = ", ".join(f"**{c.name}**" for c in targets)
            if not await confirm(message, f"Permanently delete: {names}"):
                return
            for ch in targets:
                await ch.delete(reason=f"oh hare delete by {message.author}")
            await reply(message, f"🗑️ Deleted: {names}")

        elif cmd == "hide":
            category = find_category(message.guild, arg)
            if category is None:
                available = ", ".join(c.name for c in message.guild.categories) or "none"
                await reply(message, 
                    f"Usage: `{COMMAND_PREFIX} hide <category>`. Available: {available}"
                )
                return
            everyone = message.guild.default_role
            targets = [category] + list(category.channels)
            for target in targets:
                await target.set_permissions(
                    everyone, view_channel=False, reason=f"oh hare hide by {message.author}"
                )
            await reply(message, 
                f"Hid **{category.name}** and its {len(category.channels)} channel(s) from @everyone."
            )

        elif cmd == "move":
            split = re.split(r"\s+to\s+", arg, maxsplit=1, flags=re.IGNORECASE)
            if len(split) != 2:
                await reply(message, 
                    f"Usage: `{COMMAND_PREFIX} move <from category> to <to category>`"
                )
                return
            source = find_category(message.guild, split[0])
            dest = find_category(message.guild, split[1])
            if source is None or dest is None:
                missing = split[0] if source is None else split[1]
                available = ", ".join(c.name for c in message.guild.categories) or "none"
                await reply(message, 
                    f"Category **{missing.strip()}** not found. Available: {available}"
                )
                return
            if source == dest:
                await reply(message, "Source and destination are the same category.")
                return
            channels = list(source.channels)
            if len(dest.channels) + len(channels) > 50:
                await reply(message, "Discord allows at most 50 channels per category.")
                return
            for ch in channels:
                await ch.edit(category=dest, reason=f"oh hare move by {message.author}")
            await reply(message, 
                f"Moved {len(channels)} channel(s) from **{source.name}** to **{dest.name}**."
            )

        elif cmd == "clear":
            category = find_category(message.guild, arg)
            if category is None:
                available = ", ".join(c.name for c in message.guild.categories) or "none"
                await reply(message, 
                    f"Usage: `{COMMAND_PREFIX} clear <category>`. Available: {available}"
                )
                return
            cleared = 0
            for ch in category.channels:
                if ch.overwrites:
                    await ch.edit(
                        overwrites={}, reason=f"oh hare clear by {message.author}"
                    )
                    cleared += 1
            await reply(message, 
                f"Cleared all permission overrides on {cleared} of "
                f"{len(category.channels)} channel(s) in **{category.name}**."
            )

        elif cmd == "allow":
            channels = list(message.channel_mentions)
            if message.role_mentions:
                role = message.role_mentions[0]
            else:
                role_name = re.sub(r"<#\d+>", "", arg).strip().lstrip("@")
                role = discord.utils.find(
                    lambda r: r.name.lower() == role_name.lower() or str(r.id) == role_name,
                    message.guild.roles,
                )
            if role is None or not channels:
                await reply(message, 
                    f"Usage: `{COMMAND_PREFIX} allow <@role> <#channel> [#channel ...]`"
                )
                return
            for ch in channels:
                await ch.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    reason=f"oh hare allow by {message.author}",
                )
            await reply(message, 
                f"**{role.name}** can now view and message: {' '.join(c.mention for c in channels)}"
            )

        elif cmd == "embed":
            target = message.channel_mentions[0] if message.channel_mentions else message.channel
            text = re.sub(r"<#\d+>", "", arg).strip()
            parts = [p.strip() for p in text.split("|", 2)]
            title, description, image_url = None, None, None
            if len(parts) == 1:
                description = parts[0]
            elif len(parts) == 2:
                title, description = parts
            else:
                title, description, image_url = parts
            image_file = None
            if message.attachments and message.attachments[0].content_type and \
                    message.attachments[0].content_type.startswith("image/"):
                image_file = await message.attachments[0].to_file()
            if not (title or description or image_file or image_url):
                await reply(
                    message,
                    f"Usage: `{COMMAND_PREFIX} embed [#channel] <title> | <text> | [image url]`\n"
                    "You can also attach an image to the command message.",
                )
                return
            if image_url and not re.match(r"https?://\S+$", image_url):
                await reply(message, "The image must be a direct `http(s)` link.")
                return
            if (title and len(title) > 256) or (description and len(description) > 4096):
                await reply(message, "Title max is 256 characters, text max is 4096.")
                return
            embed = discord.Embed(title=title or None, description=description or None, color=ORANGE)
            if image_file:
                embed.set_image(url=f"attachment://{image_file.filename}")
            elif image_url:
                embed.set_image(url=image_url)
            await target.send(embed=embed, file=image_file) if image_file else await target.send(embed=embed)
            if target != message.channel:
                await reply(message, f"Sent your embed to {target.mention}.")

        elif cmd == "assign":
            ch = find_voice_channel(message, arg)
            if not ch:
                await reply(message, "Voice channel not found.")
                return
            if not ch.members:
                await reply(message, f"Nobody is in {ch.mention}.")
                return
            done = []
            for member in ch.members:
                if member.bot:
                    continue
                role = discord.utils.get(message.guild.roles, name=member.name)
                if role is None:
                    role = await message.guild.create_role(
                        name=member.name, reason=f"oh hare assign by {message.author}"
                    )
                await member.add_roles(role)
                done.append(member.name)
            await reply(message, f"Assigned roles to: {', '.join(done) or 'nobody'}")

        elif cmd == "remove":
            ch = find_voice_channel(message, arg)
            if not ch:
                await reply(message, "Voice channel not found.")
                return
            pairs = []
            for member in ch.members:
                role = discord.utils.get(message.guild.roles, name=member.name)
                if role is not None:
                    pairs.append((member, role))
            if not pairs:
                await reply(message, "No matching roles to remove.")
                return
            names = ", ".join(f"**{role.name}**" for _, role in pairs)
            if not await confirm(message, f"Remove and permanently delete these roles: {names}"):
                return
            for member, role in pairs:
                await member.remove_roles(role)
                await role.delete(reason=f"oh hare remove by {message.author}")
            await reply(message, f"Removed roles from: {', '.join(m.name for m, _ in pairs)}")

        else:
            await message.channel.send(embed=help_embed())

    except discord.Forbidden:
        await reply(message, 
            "I lack permission. Give me Manage Channels/Roles, and put my role above the roles I manage."
        )
    except discord.HTTPException as e:
        await reply(message, f"Discord error: {e}")


@client.event
async def on_error(event, *args, **kwargs):
    print(f"Error in {event}:")
    traceback.print_exc()


token = os.environ.get("DISCORD_TOKEN")
if not token:
    raise SystemExit("DISCORD_TOKEN not found. Add DISCORD_TOKEN=your-token to the .env file.")
client.run(token)
