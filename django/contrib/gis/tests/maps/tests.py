# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from unittest import skipUnless

from django.contrib.gis.geos import HAS_GEOS, Point
from django.test import TestCase
from django.test.utils import override_settings

GOOGLE_MAPS_API_KEY = 'XXXX'


@skipUnless(HAS_GEOS, 'Geos is required.')
class GoogleMapsTest(TestCase):

    @override_settings(GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)
    def test_unicode_in_google_maps(self):
        """
        Test that GoogleMap doesn't crash with non-ascii content.
        """
        from django.contrib.gis.maps.google.gmap import GoogleMap, GMarker

        center = Point(6.146805, 46.227574)
        marker = GMarker(center,
                         title='En français !')
        google_map = GoogleMap(center=center, zoom=18, markers=[marker])
        self.assertIn("En français", google_map.scripts)
