import httpx
import asyncio
from discord.ext.commands import command, Cog
from embeds import DefaultEmbed, ErrorEmbed
from utils import pretty_list
import settings


class PubMedEmbed(DefaultEmbed):
    
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)
        self.set_author(
            name = "NCBI / PubMed",
            url = "https://www.ncbi.nlm.nih.gov/pmc/",
            icon_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/US-NLM-NCBI-Logo.svg/1200px-US-NLM-NCBI-Logo.svg.png"
        )


class PubChemEmbed(DefaultEmbed):
    
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)
        self.set_author(
            name = "PubChem",
            url = "https://pubchem.ncbi.nlm.nih.gov/",
            icon_url = "https://pubchemblog.files.wordpress.com/2019/12/pubchem_splash.png?w=200"
        )


class ScienceCog(Cog, name='Scientific module'):

    entrez_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    pug_url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
    
    def __init__(self, bot):
        
        self.bot = bot
        self.entrez_client = httpx.AsyncClient(base_url=self.entrez_url)
        self.pug_client = httpx.AsyncClient(base_url=self.pug_url)

    
    @command(name='articles', aliases=('papers', 'publications'))
    async def articles(self, ctx, *query):

        """Display most revelant scientific publications about a certain drug or substance.
        Additional queries and keywords are supported to refine the search."""

        query = ' '.join(query)

        try:
            async with self.entrez_client as client:
                r = await client.get(
                    "esearch.fcgi",
                    params = {
                        'retmode': 'json',
                        'db': 'pmc',
                        'sort': 'relevance',
                        'term': f'{query} AND Open Access[Filter]'
                    }
                )
                await asyncio.sleep(settings.HTTP_COOLDOWN)

                data = r.json()['esearchresult']
                count = data['count']
                ids = data['idlist']

                r = await client.get(
                    "esummary.fcgi",
                    params = {
                        'retmode': 'json',
                        'db': 'pmc',
                        'id': ','.join(ids)
                    }
                )
            
        except httpx.RequestError as e:
            await ctx.send(embed=ErrorEmbed("Can't connect to PubChem servers"))
            return

        data = r.json()['result']
        articles = []

        for uid, art_data in data.items():
            if uid != 'uids':
                title = art_data['title']
                date = art_data['pubdate']
                source = art_data['source']
                url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{uid}/"
                
                if len(title) > 112:
                    title = title[:110] + '...'

                articles.append(f"*{title}* (🗓 {date})\n🌎 {url}")
        
        embed = PubMedEmbed(
            title = "Most revelant articles about " + query,
            description = pretty_list(articles, capitalize=False)
        )

        await ctx.send(embed=embed)
    
    	
    @command(name='substance', aliases=('compound',))
    async def substance(self, ctx, substance: str):

        """Display general information about a given chemical substance or compound.
        Aliases names are supported."""

        url = self.pug_url + substance
        try:
            async with self.pug_client as client:
                r_syn = await client.get(f"{substance}/synonyms/TXT")
                await asyncio.sleep(settings.HTTP_COOLDOWN)
                r_desc = await client.get(f"{substance}/description/JSON")
                await asyncio.sleep(settings.HTTP_COOLDOWN)
                r_prop = await client.get(f"{substance}/property/MolecularFormula,MolecularWeight,IUPACName,HBondDonorCount,HBondAcceptorCount,Complexity/JSON")

        except httpx.RequestError:
            await ctx.send(embed=ErrorEmbed("Can't connect to PubChem servers"))
            return
        
        if r_syn.status_code == 404:
            await ctx.send(embed=ErrorEmbed(f"Can't find substance {substance}"))
            return
        
        synonyms = r_syn.text.split('\n')

        descriptions = r_desc.json()['InformationList']['Information']
        try:
            description = descriptions[1]['Description'] # Default value
        except IndexError:
            description = "No description avalaible 🤔"
        for provider in settings.COMPOUNDS_DESCRIPTION_PROVIDERS:
            for desc in descriptions:
                try:
                    if provider.lower() in desc['DescriptionSourceName'].lower():
                        description = desc['Description']
                        break
                except KeyError:
                    pass
        
        properties = r_prop.json()['PropertyTable']['Properties'][0]
        formula = properties['MolecularFormula']
        weight = properties['MolecularWeight']
        iupac_name = properties['IUPACName']
        h_bond_donors = properties['HBondDonorCount']
        h_bond_acceptors = properties['HBondAcceptorCount']
        complexity = properties['Complexity']

        schem_url = url + "/PNG"
        
        embed = PubChemEmbed(
            title = "Substance information: " + synonyms[0].capitalize(),
            description = description
        )
        embed.set_thumbnail(url=schem_url)
        embed.add_field(
            name = "🔬 IUPAC Name",
            value = iupac_name.capitalize(),
            inline = False
        )
        embed.add_field(
            name = "🏷 Synonyms",
            value = pretty_list(synonyms[1:7])
        )
        embed.add_field(
            name = "🧪 Formula",
            value = f"**{formula}**",
        )
        embed.add_field(
            name = "🏋 Molar mass",
            value = f"{weight} g/mol",
        )
        embed.add_field(
            name = "🔗 Hydrogen bonds",
            value = f"Donors: {h_bond_donors}\nAcceptors: {h_bond_acceptors}",
        )
        embed.add_field(
            name = "🌀 Molecular complexity",
            value = complexity,
        )

        await ctx.send(embed=embed)


    @command(name='schem', aliases=('schematic', 'draw'))
    async def schem(self, ctx, substance: str, mode: str='2d'):

        """Display the shematic of a given chemical substance or compound.
        2D and 3D modes are supported."""

        mode = mode.lower()

        if mode not in ('2d', '3d'):
            await ctx.send(embed=ErrorEmbed(f"Invalid mode {mode}", "Try with `2d` or `3d`."))
            return
        
        try:
            async with self.pug_client as client:
                r_syn = await client.get(f"{substance}/synonyms/TXT")
                await asyncio.sleep(settings.HTTP_COOLDOWN)
                r_prop = await client.get(f"{substance}/property/MolecularFormula,IUPACName/JSON")

        except httpx.RequestError:
            await ctx.send(embed=ErrorEmbed("Can't connect to PubChem servers"))
            return
        
        if r_syn.status_code == 404:
            await ctx.send(embed=ErrorEmbed(f"Can't find substance {substance}"))
            return
        
        synonyms = r_syn.text.split('\n')
        
        properties = r_prop.json()['PropertyTable']['Properties'][0]
        formula = properties['MolecularFormula']
        iupac_name = properties['IUPACName']

        schem_url = f"{self.pug_url}{substance}/PNG?record_type={mode}"
        
        embed = PubChemEmbed(
            title = "Substance schematic: " + synonyms[0].capitalize(),
        )
        embed.add_field(
            name = "🔬 IUPAC Name",
            value = iupac_name.capitalize(),
            inline = False
        )
        embed.add_field(
            name = "🧪 Formula",
            value = f"**{formula}**",
        )
        embed.set_image(url=schem_url)

        await ctx.send(embed=embed)


setup = lambda bot: bot.add_cog(ScienceCog(bot))
