from io import BytesIO

from PIL import Image, ImageDraw
import requests

from config import get_color, get_image, convert_big_value, draw_text, shit_to_name, get_top10, add_space


class Top10:
    width = 600
    height = 500
    url = 'https://api.coinmarketcap.com/v1/ticker/?limit=10'

    def create_image(self):
        img = Image.new("RGBA", (self.width, self.height), (255, 255, 255, 0))
        row = SingleRow()
        top = get_top10()
        i = 0
        for e in top:
            img.paste(row.create_image(e), (0, int(self.height / 10 * i)))
            i += 1

        img_url = 'img/big.png'
        img.save(img_url, "PNG")

    def get_url(self):
        pass


class SingleRow:
    width = 600
    height = 50
    dx = 2
    dy = 2
    s_font = 18
    m_font = 22
    l_font = 34

    def create_image(self, coin):
        coin = shit_to_name(coin)
        if coin:
            img = Image.new("RGBA", (self.width, self.height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)

            url = 'https://api.coinmarketcap.com/v1/ticker/' + coin + '/'
            rq = requests.get(url).json()[0]
            name = rq['symbol']
            price = rq['price_usd']
            market_cap = rq['market_cap_usd']
            percent_change_24h = rq['percent_change_24h']

            # Graph
            img_rq = requests.get(get_image(rq['name']))
            graph = Image.open(BytesIO(img_rq.content)).convert('RGBA')
            img.paste(graph, (self.width - graph.width - self.dx, self.dy))

            dx = (self.width - graph.width - 8) / 4
            dy = self.height / 2 - self.s_font / 2

            # Name
            draw_text(draw=draw,
                      pos=(self.dx * 3, self.height / 2 - self.m_font / 2 - 2),
                      text=name,
                      size=self.m_font,
                      font='RMM.ttf')

            # Price change
            draw_text(draw=draw,
                      pos=(self.dx + dx, dy),
                      text=add_space(percent_change_24h) + '%',
                      color=get_color(percent_change_24h),
                      size=self.s_font,
                      font='RMM.ttf')

            # Price USD
            draw_text(draw=draw,
                      pos=(self.dx + dx * 2, dy),
                      text=price + '$',
                      size=self.s_font,
                      font='RMM.ttf')

            # Price volume
            draw_text(draw=draw,
                      pos=(self.dx + dx*2, dy),
                      text=convert_big_value(market_cap) + '$',
                      size=self.s_font,
                      font='RMM.ttf')

            draw.line(xy=((0, self.height - 1), (self.width, self.height - 1)), fill=(0, 0, 0, 255), width=1)

            return img
        else:
            print('Wrong input.\nPlz try again')
            return None

