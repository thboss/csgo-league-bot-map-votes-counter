# help.py

from discord.ext import commands
import Levenshtein as lev

from . import utils


class HelpCog(commands.Cog):
    """ Handles everything related to the help menu. """

    def __init__(self, bot):
        """ Set attributes and remove default help command. """
        self.bot = bot
        self.logo = 'http://league.thboss.xyz/img/logo.jpg'
        self.bot.remove_command('help')
        self.bot.ignore_error_types.add(commands.CommandNotFound)

    def help_embed(self, title):
        embed = self.bot.embed_template(title=title)
        prefix = self.bot.command_prefix
        prefix = prefix[0] if prefix is not str else prefix

        for cog in self.bot.cogs:  # Uset bot.cogs instead of bot.commands to control ordering in the help embed
            for cmd in self.bot.get_cog(cog).get_commands():
                if cmd.usage:  # Command has usage attribute set
                    embed.add_field(name=f'**{prefix}{cmd.usage}**', value=f'_{cmd.brief}_', inline=False)
                else:
                    embed.add_field(name=f'**{prefix}{cmd.name}**', value=f'_{cmd.brief}_', inline=False)

        return embed

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """ Send help message when a mis-entered command is received. """
        if type(error) is commands.CommandNotFound:
            # Get Levenshtein distance from commands
            in_cmd = ctx.invoked_with
            bot_cmds = list(self.bot.commands)
            lev_dists = [lev.distance(in_cmd, str(cmd)) / max(len(in_cmd), len(str(cmd))) for cmd in bot_cmds]
            lev_min = min(lev_dists)

            # Prep help message title
            embed_title = utils.translate('help-not-valid', ctx.message.content)
            prefixes = self.bot.command_prefix
            prefix = prefixes[0] if prefixes is not str else prefixes  # Prefix can be string or iterable of strings

            # Make suggestion if lowest Levenshtein distance is under threshold
            if lev_min <= 0.5:
                embed_title += utils.translate('help-did-you-mean') + f' `{prefix}{bot_cmds[lev_dists.index(lev_min)]}`?'
            else:
                embed_title += utils.translate('help-use-help', prefix)

            embed = self.bot.embed_template(title=embed_title)
            await ctx.send(embed=embed)

    @commands.command(brief=utils.translate('help-brief'))
    async def help(self, ctx):
        """ Generate and send help embed based on the bot's commands. """
        embed = self.help_embed(utils.translate('help-bot-commands'))
        await ctx.send(embed=embed)

    @commands.command(brief=utils.translate('help-info-brief'))
    async def info(self, ctx):
        """ Display the info embed. """
        description = (
            f'{utils.translate("help-bot-description")}'
        )
        embed = self.bot.embed_template(title='__G5 Bot__', description=description)
        embed.set_thumbnail(url=self.logo)
        await ctx.send(embed=embed)
