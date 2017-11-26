from functools import partial
import weakref

from bokeh.plotting import figure, ColumnDataSource
from bokeh.models import HoverTool, Button, Select
from bokeh.layouts import column, row
from bokeh.server.server import Server

from . import profile
from .utils import log_errors


class ProfileTimePlot(object):
    """ Time plots of the current resource usage on the cluster

    This is two plots, one for CPU and Memory and another for Network I/O
    """
    def __init__(self, profiler, doc=None, **kwargs):
        if doc is not None:
            self.doc = weakref.ref(doc)
            try:
                self.key = doc.session_context.request.arguments.get('key', None)
            except AttributeError:
                self.key = None
            if isinstance(self.key, list):
                self.key = self.key[0]
            if isinstance(self.key, bytes):
                self.key = self.key.decode()
            self.task_names = ['All', self.key]
        else:
            self.key = None
            self.task_names = ['All']

        self.profiler = profiler
        self.start = None
        self.stop = None
        self.ts = {'count': [], 'time': []}
        self.state = profile.create()
        data = profile.plot_data(self.state, self.profiler.trigger_interval / 1000)
        self.states = data.pop('states')
        self.source = ColumnDataSource(data=data)

        def cb(attr, old, new):
            with log_errors():
                try:
                    ind = new['1d']['indices'][0]
                except IndexError:
                    return
                data = profile.plot_data(self.states[ind], self.profiler.trigger_interval / 1000)
                del self.states[:]
                self.states.extend(data.pop('states'))
                self.source.data.update(data)
                self.source.selected = old

        self.source.on_change('selected', cb)

        self.profile_plot = figure(tools='tap', height=400, **kwargs)
        self.profile_plot.quad('left', 'right', 'top', 'bottom', color='color',
                               line_color='black', source=self.source)

        hover = HoverTool(
            point_policy="follow_mouse",
            tooltips="""
                <div>
                    <span style="font-size: 14px; font-weight: bold;">Name:</span>&nbsp;
                    <span style="font-size: 10px; font-family: Monaco, monospace;">@name</span>
                </div>
                <div>
                    <span style="font-size: 14px; font-weight: bold;">Filename:</span>&nbsp;
                    <span style="font-size: 10px; font-family: Monaco, monospace;">@filename</span>
                </div>
                <div>
                    <span style="font-size: 14px; font-weight: bold;">Line number:</span>&nbsp;
                    <span style="font-size: 10px; font-family: Monaco, monospace;">@line_number</span>
                </div>
                <div>
                    <span style="font-size: 14px; font-weight: bold;">Line:</span>&nbsp;
                    <span style="font-size: 10px; font-family: Monaco, monospace;">@line</span>
                </div>
                <div>
                    <span style="font-size: 14px; font-weight: bold;">Time:</span>&nbsp;
                    <span style="font-size: 10px; font-family: Monaco, monospace;">@time</span>
                </div>
                """
        )
        self.profile_plot.add_tools(hover)

        self.profile_plot.xaxis.visible = False
        self.profile_plot.yaxis.visible = False
        self.profile_plot.grid.visible = False

        self.ts_source = ColumnDataSource({'time': [], 'count': []})
        self.ts_plot = figure(title='Activity over time', height=100,
                              x_axis_type='datetime', active_drag='xbox_select',
                              tools='xpan,xwheel_zoom,xbox_select,reset',
                              **kwargs)
        self.ts_plot.line('time', 'count', source=self.ts_source)
        self.ts_plot.circle('time', 'count', source=self.ts_source, color=None,
                            selection_color='orange')
        self.ts_plot.yaxis.visible = False
        self.ts_plot.grid.visible = False

        def ts_change(attr, old, new):
            with log_errors():
                selected = self.ts_source.selected['1d']['indices']
                if selected:
                    start = self.ts_source.data['time'][min(selected)] / 1000
                    stop = self.ts_source.data['time'][max(selected)] / 1000
                    self.start, self.stop = min(start, stop), max(start, stop)
                else:
                    self.start = self.stop = None
                self.trigger_update(update_metadata=False)

        self.ts_source.on_change('selected', ts_change)

        self.reset_button = Button(label="Reset", button_type="success")
        self.reset_button.on_click(lambda: self.update(self.state) )

        self.update_button = Button(label="Update", button_type="success")
        self.update_button.on_click(self.trigger_update)

        self.select = Select(value=self.task_names[-1], options=self.task_names)

        def select_cb(attr, old, new):
            if new == 'All':
                new = None
            self.key = new
            self.trigger_update(update_metadata=False)

        self.select.on_change('value', select_cb)

        self.root = column(row(self.reset_button,
                               self.update_button, sizing_mode='scale_width'),
                           self.profile_plot, self.ts_plot, **kwargs)

    def update(self, state, metadata=None):
        with log_errors():
            self.state = state
            data = profile.plot_data(self.state, self.profiler.trigger_interval / 1000)
            self.states = data.pop('states')
            self.source.data.update(data)

            if metadata is not None and metadata['counts']:
                ts = metadata['counts']
                times, counts = zip(*ts)
                self.ts = {'count': counts, 'time': [t * 1000 for t in times]}

                self.ts_source.data.update(self.ts)

    def trigger_update(self, update_metadata=True):
        def cb():
            with log_errors():
                prof = self.profiler.get_profile(start=self.start, stop=self.stop)
                if update_metadata:
                    metadata = self.profiler.get_profile_metadata()
                else:
                    metadata = None
                self.doc().add_next_tick_callback(lambda: self.update(prof, metadata))

        self.profiler.io_loop.add_callback(cb)


def profile_doc(profiler, doc):
    doc.title = 'Profile'
    prof = ProfileTimePlot(profiler, sizing_mode='scale_width', doc=doc)
    doc.add_root(prof.root)

    prof.trigger_update()


def serve(profiler, **kwargs):
    server = Server({'/main': partial(profile_doc, profiler)},
                    io_loop=profiler.io_loop,
                    **kwargs)
    profiler.io_loop.add_callback(server.start)
    return server
